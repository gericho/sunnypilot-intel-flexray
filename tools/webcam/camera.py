import os
import time

import cv2 as cv
import numpy as np

class Camera:
  def __init__(self, cam_type_state, stream_type, camera_id):
    try:
      camera_id = int(camera_id)
    except ValueError: # allow strings, ex: /dev/video0
      pass
    self.cam_type_state = cam_type_state
    self.stream_type = stream_type
    self.cur_frame_id = 0

    print(f"Opening {cam_type_state} at {camera_id}")

    self.cap = cv.VideoCapture(camera_id)

    # Use per-camera env settings from go.sh when available.
    if cam_type_state == "driverCameraState":
      w = float(os.getenv("DRIVER_W", "1280"))
      h = float(os.getenv("DRIVER_H", "720"))
      fps = float(os.getenv("DRIVER_FPS", "20"))
    elif cam_type_state == "wideRoadCameraState":
      w = float(os.getenv("WIDE_W", os.getenv("ROAD_W", "1280")))
      h = float(os.getenv("WIDE_H", os.getenv("ROAD_H", "720")))
      fps = float(os.getenv("WIDE_FPS", os.getenv("ROAD_FPS", "20")))
    else:
      w = float(os.getenv("ROAD_W", "1280"))
      h = float(os.getenv("ROAD_H", "720"))
      fps = float(os.getenv("ROAD_FPS", "20"))

    self.fps = fps

    self.cap.set(cv.CAP_PROP_FRAME_WIDTH, w)
    self.cap.set(cv.CAP_PROP_FRAME_HEIGHT, h)
    self.cap.set(cv.CAP_PROP_FPS, fps)

    self.W = self.cap.get(cv.CAP_PROP_FRAME_WIDTH)
    self.H = self.cap.get(cv.CAP_PROP_FRAME_HEIGHT)
    self.nv12_backend = os.getenv("WEBCAM_NV12_BACKEND", "opencv").strip().lower()
    self.flip_mode = os.getenv("WEBCAM_FLIP", "-1").strip().lower()
    self.flip_code = None if self.flip_mode in ("none", "off", "") else int(self.flip_mode)
    self.profile = os.getenv("WEBCAM_PROFILE", "0").strip().lower() in ("1", "true", "yes", "on")

    self._frame_w = 0
    self._frame_h = 0
    self._nv12_buf = None
    self._uv_buf = None

  def _ensure_nv12_buffers(self, w, h):
    if self._frame_w == w and self._frame_h == h and self._nv12_buf is not None:
      return
    self._frame_w = w
    self._frame_h = h
    self._nv12_buf = np.empty((h * 3 // 2, w), dtype=np.uint8)
    self._uv_buf = np.empty((h // 2, w), dtype=np.uint8)

  def _bgr2nv12_opencv(self, bgr):
    h, w = bgr.shape[:2]
    self._ensure_nv12_buffers(w, h)

    i420 = cv.cvtColor(bgr, cv.COLOR_BGR2YUV_I420)
    self._nv12_buf[:h, :] = i420[:h, :]

    y_size = w * h
    flat = i420.reshape(-1)
    u = flat[y_size:y_size + (y_size // 4)].reshape(h // 2, w // 2)
    v = flat[y_size + (y_size // 4):y_size + (y_size // 2)].reshape(h // 2, w // 2)
    self._uv_buf[:, 0::2] = u
    self._uv_buf[:, 1::2] = v
    self._nv12_buf[h:, :] = self._uv_buf
    return self._nv12_buf

  def _bgr2nv12_legacy(self, bgr):
    import av
    frame = av.VideoFrame.from_ndarray(bgr, format='bgr24')
    return frame.reformat(format='nv12').to_ndarray()

  def bgr2nv12(self, bgr):
    if self.nv12_backend == "legacy":
      return self._bgr2nv12_legacy(bgr)
    return self._bgr2nv12_opencv(bgr)

  def read_frames(self):
    while True:
      t0 = time.perf_counter() if self.profile else 0.0
      ret, frame = self.cap.read()
      read_ms = (time.perf_counter() - t0) * 1000.0 if self.profile else 0.0
      if not ret:
        break
      flip_ms = 0.0
      if self.flip_code is not None:
        t1 = time.perf_counter() if self.profile else 0.0
        frame = cv.flip(frame, self.flip_code)
        flip_ms = (time.perf_counter() - t1) * 1000.0 if self.profile else 0.0
      t2 = time.perf_counter() if self.profile else 0.0
      yuv = self.bgr2nv12(frame)
      convert_ms = (time.perf_counter() - t2) * 1000.0 if self.profile else 0.0
      # VisionIpcServer.send accepts a contiguous byte view, so avoid per-frame tobytes() copies.
      t3 = time.perf_counter() if self.profile else 0.0
      payload = memoryview(yuv).cast('B')
      payload_ms = (time.perf_counter() - t3) * 1000.0 if self.profile else 0.0
      if self.profile:
        yield payload, {
          "read_ms": read_ms,
          "flip_ms": flip_ms,
          "convert_ms": convert_ms,
          "payload_ms": payload_ms,
        }
      else:
        yield payload, None
    self.cap.release()
