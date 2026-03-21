import os


def is_pc_webcam_runtime() -> bool:
  return os.getenv("SP_DEVICE_TYPE") == "PC" and os.getenv("USE_WEBCAM") == "1"


def get_selfdrived_init_timeout(default_timeout: float = 6.0) -> float:
  return 20.0 if is_pc_webcam_runtime() else default_timeout


def get_selfdrived_packets(
  gps_packets: list[str],
  sensor_packets: list[str],
  camera_packets: list[str],
) -> tuple[list[str], list[str], list[str]]:
  if not is_pc_webcam_runtime():
    return gps_packets, sensor_packets, camera_packets
  return [], [], ["roadCameraState"]


def configure_tinygrad_runtime(default_device: str) -> None:
  if is_pc_webcam_runtime():
    os.environ["DEV"] = "CL"
  else:
    os.environ.setdefault("DEV", default_device)

  if "USBGPU" in os.environ:
    os.environ["DEV"] = "AMD"
    os.environ["AMD_IFACE"] = "USB"

  from tinygrad.helpers import getenv as tinygrad_getenv
  from tinygrad.device import Device

  tinygrad_getenv.cache_clear()
  Device.__dict__.pop("DEFAULT", None)

