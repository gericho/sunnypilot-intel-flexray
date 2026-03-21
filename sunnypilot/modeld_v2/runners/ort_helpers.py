import itertools
import json
import os
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort

ORT_TYPES_TO_NP_TYPES = {'tensor(float16)': np.float16, 'tensor(float)': np.float32, 'tensor(uint8)': np.uint8}

def attributeproto_fp16_to_fp32(attr):
  float32_list = np.frombuffer(attr.raw_data, dtype=np.float16)
  attr.data_type = 1
  attr.raw_data = float32_list.astype(np.float32).tobytes()

def convert_fp16_to_fp32(model):
  for i in model.graph.initializer:
    if i.data_type == 10:
      attributeproto_fp16_to_fp32(i)
  for i in itertools.chain(model.graph.input, model.graph.output):
    if i.type.tensor_type.elem_type == 10:
      i.type.tensor_type.elem_type = 1
  for i in model.graph.node:
    if i.op_type == 'Cast' and i.attribute[0].i == 10:
      i.attribute[0].i = 1
    for a in i.attribute:
      if hasattr(a, 't'):
        if a.t.data_type == 10:
          attributeproto_fp16_to_fp32(a.t)
  return model.SerializeToString()


def _normalize_bool(value) -> bool:
  if isinstance(value, bool):
    return value
  return str(value).strip().lower() in ("1", "true", "yes", "on")


def _get_session_options():
  options = ort.SessionOptions()
  options.intra_op_num_threads = int(os.getenv("ORT_INTRA_OP_THREADS", "4"))
  options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
  options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
  return options


def make_onnx_cpu_runner(model_path):
  options = _get_session_options()
  model_data = convert_fp16_to_fp32(onnx.load(model_path))
  return ort.InferenceSession(model_data, options, providers=['CPUExecutionProvider'])


def make_onnx_runner(model_path):
  backend = os.getenv("ORT_BACKEND", "cpu").strip().lower()
  if backend == "openvino":
    options = _get_session_options()
    # ORT OpenVINO docs recommend disabling ORT graph-level optimization and
    # letting OpenVINO perform the backend-specific graph optimizations.
    if _normalize_bool(os.getenv("ORT_OPENVINO_DISABLE_ORT_OPT", "1")):
      options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL

    device = os.getenv("ORT_OPENVINO_DEVICE", "GPU").strip().upper()
    fallback_cpu = _normalize_bool(os.getenv("ORT_OPENVINO_FALLBACK_CPU", "1"))
    ov_options = {'device_type': device}

    performance_hint = os.getenv("ORT_OPENVINO_PERFORMANCE_HINT", "LATENCY").strip().upper()
    execution_mode = os.getenv("ORT_OPENVINO_EXECUTION_MODE", "").strip().upper()
    num_streams = os.getenv("ORT_OPENVINO_NUM_STREAMS", "").strip()
    cache_dir = os.getenv("ORT_OPENVINO_CACHE_DIR", "").strip()
    if not cache_dir:
      cache_dir = str(Path(__file__).resolve().parents[4] / ".cache" / "openvino_model_cache")
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    load_config = {
      device: {
        "PERFORMANCE_HINT": performance_hint,
        "CACHE_DIR": cache_dir,
      }
    }
    if execution_mode:
      load_config[device]["EXECUTION_MODE_HINT"] = execution_mode
    if num_streams:
      load_config[device]["NUM_STREAMS"] = num_streams

    ov_options["load_config"] = json.dumps(load_config)
    providers = [('OpenVINOExecutionProvider', ov_options)]
    if fallback_cpu:
      providers.append('CPUExecutionProvider')
    return ort.InferenceSession(str(model_path), options, providers=providers)

  return make_onnx_cpu_runner(model_path)
