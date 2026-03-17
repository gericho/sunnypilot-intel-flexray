from pathlib import Path

import numpy as np
import os
import time

from openpilot.sunnypilot.modeld_v2.constants import ModelConstants
from openpilot.sunnypilot.modeld_v2.runners.ort_helpers import ORT_TYPES_TO_NP_TYPES, make_onnx_runner
from openpilot.sunnypilot.models.runners.constants import CLMemDict, FrameDict, ModelType, NumpyDict, ShapeDict, SliceDict
from openpilot.sunnypilot.models.runners.model_runner import DEFAULT_MODEL_DIR, ModelRunner
from openpilot.sunnypilot.models.runners.tinygrad.model_types import OffPolicyTinygrad, PolicyTinygrad, SupercomboTinygrad, VisionTinygrad
from openpilot.sunnypilot.models.split_model_constants import SplitModelConstants


class ONNXModelRunner(ModelRunner, SupercomboTinygrad, PolicyTinygrad, VisionTinygrad, OffPolicyTinygrad):
  def __init__(self, model_type: int = ModelType.supercombo):
    ModelRunner.__init__(self)
    SupercomboTinygrad.__init__(self)
    PolicyTinygrad.__init__(self)
    VisionTinygrad.__init__(self)
    OffPolicyTinygrad.__init__(self)
    self._constants = ModelConstants
    self._model_data = self.models.get(model_type)
    if not self._model_data or not self._model_data.model:
      raise ValueError(f"Model data for type {model_type} not available.")

    self.runner = make_onnx_runner(self._get_onnx_path())
    self.input_to_nptype = {
      model_input.name: ORT_TYPES_TO_NP_TYPES[model_input.type]
      for model_input in self.runner.get_inputs()
    }
    self.profile_stats = {
      "numpy_inputs_ms": 0.0,
      "cl_to_numpy_ms": 0.0,
      "onnx_run_ms": 0.0,
    }

  def warmup(self) -> None:
    warmup_runs = int(os.getenv("ORT_WARMUP_RUNS", "2"))
    if warmup_runs <= 0:
      return
    dummy_inputs = {}
    for model_input in self.runner.get_inputs():
      dtype = ORT_TYPES_TO_NP_TYPES[model_input.type]
      shape = tuple(int(x) for x in model_input.shape)
      dummy_inputs[model_input.name] = np.zeros(shape, dtype=dtype)
    for _ in range(warmup_runs):
      self.runner.run(None, dummy_inputs)

  def _get_onnx_path(self) -> Path:
    artifact_path = Path(getattr(self._model_data.model.artifact, "path", ""))
    artifact_name = self._model_data.model.artifact.fileName

    if artifact_path:
      if artifact_path.suffix == ".onnx":
        return artifact_path
      if artifact_path.name.endswith("_tinygrad.pkl"):
        return artifact_path.with_name(artifact_path.name.replace("_tinygrad.pkl", ".onnx"))

    if artifact_name.endswith("_tinygrad.pkl"):
      return DEFAULT_MODEL_DIR / artifact_name.replace("_tinygrad.pkl", ".onnx")
    if artifact_name.endswith(".onnx"):
      return DEFAULT_MODEL_DIR / artifact_name

    raise ValueError(f"Cannot derive ONNX path from artifact {artifact_name}")

  @property
  def input_shapes(self) -> ShapeDict:
    return {runner_input.name: runner_input.shape for runner_input in self.runner.get_inputs()}

  @property
  def vision_input_names(self) -> list[str]:
    return [name for name in self.input_shapes.keys() if 'img' in name]

  def prepare_inputs(self, imgs_cl: CLMemDict, numpy_inputs: NumpyDict, frames: FrameDict) -> dict:
    t0 = time.perf_counter()
    self.inputs = {
      key: value.astype(dtype=self.input_to_nptype.get(key, value.dtype), copy=False)
      for key, value in numpy_inputs.items()
    }
    t1 = time.perf_counter()
    cl_to_numpy_ms = 0.0
    for key in imgs_cl:
      cl_t0 = time.perf_counter()
      buffer = frames[key].buffer_from_cl(imgs_cl[key])
      reshaped_buffer = buffer.reshape(self.input_shapes[key])
      self.inputs[key] = reshaped_buffer.astype(dtype=self.input_to_nptype[key])
      cl_to_numpy_ms += (time.perf_counter() - cl_t0) * 1000.0
    self.profile_stats["numpy_inputs_ms"] = (t1 - t0) * 1000.0
    self.profile_stats["cl_to_numpy_ms"] = cl_to_numpy_ms
    return self.inputs

  def _parse_outputs(self, model_outputs: np.ndarray) -> NumpyDict:
    if self._model_data is None:
      raise ValueError("Model data is not available. Ensure the model is loaded correctly.")
    return self.parser_method_dict[self._model_data.model.type.raw](model_outputs)

  def _run_model(self) -> NumpyDict:
    t0 = time.perf_counter()
    outputs = self.runner.run(None, self.inputs)[0].astype(np.float32, copy=False).flatten()
    self.profile_stats["onnx_run_ms"] = (time.perf_counter() - t0) * 1000.0
    return self._parse_outputs(outputs)


class ONNXSplitRunner(ModelRunner):
  def __init__(self):
    super().__init__()
    self.is_20hz_3d = True
    self.vision_runner = ONNXModelRunner(ModelType.vision)
    self.policy_runner = ONNXModelRunner(ModelType.policy)
    self.off_policy_runner = ONNXModelRunner(ModelType.offPolicy) if self.models.get(ModelType.offPolicy) else None
    self._constants = SplitModelConstants
    self.profile_stats = {
      "policy_onnx_ms": 0.0,
      "vision_onnx_ms": 0.0,
      "off_policy_onnx_ms": 0.0,
      "numpy_inputs_ms": 0.0,
      "cl_to_numpy_ms": 0.0,
      "prepare_inputs_ms": 0.0,
      "onnx_run_ms": 0.0,
    }

  def warmup(self) -> None:
    self.policy_runner.warmup()
    self.vision_runner.warmup()
    if self.off_policy_runner:
      self.off_policy_runner.warmup()

  def _run_model(self) -> NumpyDict:
    t0 = time.perf_counter()
    policy_output = self.policy_runner.run_model()
    t1 = time.perf_counter()
    vision_output = self.vision_runner.run_model()
    t2 = time.perf_counter()
    outputs = {**policy_output, **vision_output}
    if self.off_policy_runner:
      outputs.update(self.off_policy_runner.run_model())
    t3 = time.perf_counter()
    self.profile_stats["policy_onnx_ms"] = (t1 - t0) * 1000.0
    self.profile_stats["vision_onnx_ms"] = (t2 - t1) * 1000.0
    self.profile_stats["off_policy_onnx_ms"] = (t3 - t2) * 1000.0 if self.off_policy_runner else 0.0
    self.profile_stats["onnx_run_ms"] = (t3 - t0) * 1000.0
    return outputs

  @property
  def vision_input_names(self) -> list[str]:
    return list(self.vision_runner.vision_input_names)

  @property
  def input_shapes(self) -> ShapeDict:
    shapes = {**self.policy_runner.input_shapes, **self.vision_runner.input_shapes}
    if self.off_policy_runner:
      shapes.update(self.off_policy_runner.input_shapes)
    return shapes

  @property
  def output_slices(self) -> SliceDict:
    slices = {**self.policy_runner.output_slices, **self.vision_runner.output_slices}
    if self.off_policy_runner:
      slices.update(self.off_policy_runner.output_slices)
    return slices

  def prepare_inputs(self, imgs_cl: CLMemDict, numpy_inputs: NumpyDict, frames: FrameDict) -> dict:
    t0 = time.perf_counter()
    self.policy_runner.prepare_inputs({}, numpy_inputs, frames)
    t1 = time.perf_counter()
    self.vision_runner.prepare_inputs(imgs_cl, {}, frames)
    t2 = time.perf_counter()
    inputs = {**self.policy_runner.inputs, **self.vision_runner.inputs}
    if self.off_policy_runner:
      self.off_policy_runner.prepare_inputs({}, numpy_inputs, frames)
      inputs.update(self.off_policy_runner.inputs)
    t3 = time.perf_counter()
    self.profile_stats["prepare_inputs_ms"] = (t3 - t0) * 1000.0
    self.profile_stats["numpy_inputs_ms"] = self.policy_runner.profile_stats["numpy_inputs_ms"]
    self.profile_stats["cl_to_numpy_ms"] = self.vision_runner.profile_stats["cl_to_numpy_ms"]
    return inputs
