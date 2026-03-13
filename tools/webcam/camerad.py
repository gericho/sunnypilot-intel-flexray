#!/usr/bin/env python3
import threading
import os
import platform
import time
from collections import namedtuple

from msgq.visionipc import VisionIpcServer, VisionStreamType
from cereal import messaging

from openpilot.tools.webcam.camera import Camera
from openpilot.common.realtime import Ratekeeper

ROAD_CAM = os.getenv("ROAD_CAM", "0")
WIDE_CAM = os.getenv("WIDE_CAM")
DRIVER_CAM = os.getenv("DRIVER_CAM")
WEBCAM_PROFILE = os.getenv("WEBCAM_PROFILE", "0").strip().lower() in ("1", "true", "yes", "on")
PROFILE_INTERVAL_S = float(os.getenv("WEBCAM_PROFILE_INTERVAL", "5"))

CameraType = namedtuple("CameraType", ["msg_name", "stream_type", "cam_id"])

CAMERAS = [
  CameraType("roadCameraState", VisionStreamType.VISION_STREAM_ROAD, ROAD_CAM)
]
if WIDE_CAM:
  CAMERAS.append(CameraType("wideRoadCameraState", VisionStreamType.VISION_STREAM_WIDE_ROAD, WIDE_CAM))
if DRIVER_CAM:
  CAMERAS.append(CameraType("driverCameraState", VisionStreamType.VISION_STREAM_DRIVER, DRIVER_CAM))

class Camerad:
  def __init__(self):
    self.pm = messaging.PubMaster([c.msg_name for c in CAMERAS])
    self.vipc_server = VisionIpcServer("camerad")

    self.cameras = []
    for c in CAMERAS:
      cam_device = f"/dev/video{c.cam_id}" if platform.system() != "Darwin" else c.cam_id
      cam = Camera(c.msg_name, c.stream_type, cam_device)
      self.cameras.append(cam)
      self.vipc_server.create_buffers(c.stream_type, 20, cam.W, cam.H)

    self.vipc_server.start_listener()

  def _send_yuv(self, yuv, frame_id, pub_type, yuv_type):
    # Use monotonic timestamps in ns (same time domain expected by loggerd/Cabana).
    # frame_id-relative timestamps break playback/signal sync.
    eof_ns = time.monotonic_ns()
    self.vipc_server.send(yuv_type, yuv, frame_id, eof_ns, eof_ns)
    dat = messaging.new_message(pub_type, valid=True)
    msg = {
      "frameId": frame_id,
      "transform": [1.0, 0.0, 0.0,
                    0.0, 1.0, 0.0,
                    0.0, 0.0, 1.0]
    }
    setattr(dat, pub_type, msg)
    self.pm.send(pub_type, dat)

  def camera_runner(self, cam):
    rk = Ratekeeper(max(1.0, float(cam.fps)), None)
    interval_start = time.monotonic()
    frame_count = 0
    sums = {
      "read_ms": 0.0,
      "flip_ms": 0.0,
      "convert_ms": 0.0,
      "payload_ms": 0.0,
      "send_ms": 0.0,
    }

    for yuv, stage in cam.read_frames():
      t_send = time.perf_counter() if WEBCAM_PROFILE else 0.0
      self._send_yuv(yuv, cam.cur_frame_id, cam.cam_type_state, cam.stream_type)
      send_ms = (time.perf_counter() - t_send) * 1000.0 if WEBCAM_PROFILE else 0.0
      cam.cur_frame_id += 1
      if WEBCAM_PROFILE and stage is not None:
        frame_count += 1
        sums["read_ms"] += stage["read_ms"]
        sums["flip_ms"] += stage["flip_ms"]
        sums["convert_ms"] += stage["convert_ms"]
        sums["payload_ms"] += stage["payload_ms"]
        sums["send_ms"] += send_ms

        now = time.monotonic()
        elapsed = now - interval_start
        if elapsed >= PROFILE_INTERVAL_S:
          fps = frame_count / elapsed if elapsed > 0 else 0.0
          print(
            f"[webcamerad:{cam.cam_type_state}] fps={fps:.2f} "
            f"read_ms={sums['read_ms']/frame_count:.3f} "
            f"flip_ms={sums['flip_ms']/frame_count:.3f} "
            f"convert_ms={sums['convert_ms']/frame_count:.3f} "
            f"payload_ms={sums['payload_ms']/frame_count:.3f} "
            f"send_ms={sums['send_ms']/frame_count:.3f} "
            f"backend={cam.nv12_backend} flip={cam.flip_mode}"
          )
          interval_start = now
          frame_count = 0
          for k in sums:
            sums[k] = 0.0
      rk.keep_time()

  def run(self):
    threads = []
    for cam in self.cameras:
      cam_thread = threading.Thread(target=self.camera_runner, args=(cam,))
      cam_thread.start()
      threads.append(cam_thread)

    for t in threads:
      t.join()


def main():
  camerad = Camerad()
  camerad.run()


if __name__ == "__main__":
  main()
