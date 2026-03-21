import os
from pathlib import Path
from types import SimpleNamespace

from openpilot.sunnypilot.models.runners.constants import ModelType


def get_forced_model_runner() -> str:
  return os.getenv("FORCE_MODEL_RUNNER", "").strip().lower()


def get_default_split_models(default_model_dir: Path) -> list[SimpleNamespace]:
  return [
    SimpleNamespace(
      type=SimpleNamespace(raw=ModelType.vision),
      artifact=SimpleNamespace(
        fileName="driving_vision_tinygrad.pkl",
        path=str(default_model_dir / "driving_vision_tinygrad.pkl"),
      ),
      metadata=SimpleNamespace(
        fileName="driving_vision_metadata.pkl",
        path=str(default_model_dir / "driving_vision_metadata.pkl"),
      ),
    ),
    SimpleNamespace(
      type=SimpleNamespace(raw=ModelType.policy),
      artifact=SimpleNamespace(
        fileName="driving_policy_tinygrad.pkl",
        path=str(default_model_dir / "driving_policy_tinygrad.pkl"),
      ),
      metadata=SimpleNamespace(
        fileName="driving_policy_metadata.pkl",
        path=str(default_model_dir / "driving_policy_metadata.pkl"),
      ),
    ),
  ]

