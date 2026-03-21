from openpilot.sunnypilot.models.helpers import get_active_bundle
import os

from openpilot.sunnypilot.models.runners.model_runner import ModelRunner
from openpilot.sunnypilot.models.runners.onnx.onnx_runner import ONNXModelRunner, ONNXSplitRunner
from openpilot.sunnypilot.models.runners.tinygrad.tinygrad_runner import TinygradRunner, TinygradSplitRunner
from openpilot.sunnypilot.models.runners.constants import ModelType


def _use_onnx() -> bool:
  return str(os.getenv("USE_ONNX", "")).strip().lower() in ("1", "true", "yes", "on")


def get_model_runner() -> ModelRunner:
  """
  Factory function to create and return the appropriate ModelRunner instance.

  Selects TinygradRunner, choosing TinygradSplitRunner if separate vision/policy
  models are detected in the active bundle.

  :return: An instance of a ModelRunner subclass (ONNXRunner, TinygradRunner, or TinygradSplitRunner).
  """
  bundle = get_active_bundle()
  if _use_onnx():
    if bundle and bundle.models:
      model_types = {m.type.raw for m in bundle.models}
      if ModelType.vision in model_types or ModelType.policy in model_types:
        return ONNXSplitRunner()
      return ONNXModelRunner(bundle.models[0].type.raw)
    return ONNXSplitRunner()

  if bundle and bundle.models:
    model_types = {m.type.raw for m in bundle.models}
    if ModelType.vision in model_types or ModelType.policy in model_types:
      return TinygradSplitRunner()
    if bundle.models:
      return TinygradRunner(bundle.models[0].type.raw)

  return TinygradRunner(ModelType.supercombo)
