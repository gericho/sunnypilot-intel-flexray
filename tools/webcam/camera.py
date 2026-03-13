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
      fourcc = os.getenv("DRIVER_FOURCC", "YUYV").strip().upper()
    elif cam_type_state == "wideRoadCameraState":
      w = float(os.getenv("WIDE_W", os.getenv("ROAD_W", "1280")))
      h = float(os.getenv("WIDE_H", os.getenv("ROAD_H", "720")))
      fps = float(os.getenv("WIDE_FPS", os.getenv("ROAD_FPS", "20")))
      fourcc = os.getenv("WIDE_FOURCC", os.getenv("ROAD_FOURCC", "NV12")).strip().upper()
    else:
      w = float(os.getenv("ROAD_W", "1280"))
      h = float(os.getenv("ROAD_H", "720"))
      fps = float(os.getenv("ROAD_FPS", "20"))
      fourcc = os.getenv("ROAD_FOURCC", "NV12").strip().upper()

    self.fps = fps

    if len(fourcc) == 4:
      self.cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*fourcc))
    self.cap.set(cv.CAP_PROP_FRAME_WIDTH, w)
    self.cap.set(cv.CAP_PROP_FRAME_HEIGHT, h)
    self.cap.set(cv.CAP_PROP_FPS, fps)

    self.W = self.cap.get(cv.CAP_PROP_FRAME_WIDTH)
    self.H = self.cap.get(cv.CAP_PROP_FRAME_HEIGHT)
    self.w_int = int(self.W)
    self.h_int = int(self.H)
    self.nv12_backend = os.getenv("WEBCAM_NV12_BACKEND", "opencv").strip().lower()
    self.flip_mode = os.getenv("WEBCAM_FLIP", "-1").strip().lower()
    self.flip_code = None if self.flip_mode in ("none", "off", "") else int(self.flip_mode)
    self.profile = os.getenv("WEBCAM_PROFILE", "0").strip().lower() in ("1", "true", "yes", "on")
    self.raw_nv12_enabled = os.getenv("WEBCAM_RAW_NV12", "1").strip().lower() in ("1", "true", "yes", "on")
    self._raw_nv12_active = False
    self._raw_nv12_probed = False

    # Fast path: if backend can deliver NV12 raw frames, skip BGR->NV12 conversion.
    # Flip on raw NV12 is not handled here, so keep RGB conversion when flip is requested.
    if self.raw_nv12_enabled and self.flip_code is None:
      self.cap.set(cv.CAP_PROP_CONVERT_RGB, 0)

    self._frame_w = 0
    self._frame_h = 0
    self._nv12_buf = None
    self._uv_buf = None

  def _is_nv12_frame(self, frame):
    if frame is None or frame.dtype != np.uint8:
      return False
    expected = self.w_int * self.h_int * 3 // 2
    return frame.size == expected

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

      if not self._raw_nv12_probed:
        self._raw_nv12_probed = True
        self._raw_nv12_active = self._is_nv12_frame(frame)
        print(f"[webcamerad:{self.cam_type_state}] raw_nv12={'active' if self._raw_nv12_active else 'inactive'}")
        if self.raw_nv12_enabled and self.flip_code is None and not self._raw_nv12_active:
          # Backend did not expose raw NV12, restore default OpenCV BGR conversion.
          self.cap.set(cv.CAP_PROP_CONVERT_RGB, 1)

      if self._raw_nv12_active:
        yuv = frame if frame.flags["C_CONTIGUOUS"] else np.ascontiguousarray(frame)
        payload = memoryview(yuv).cast('B')
        if self.profile:
          yield payload, {
            "read_ms": read_ms,
            "flip_ms": 0.0,
            "convert_ms": 0.0,
            "payload_ms": 0.0,
          }
        else:
          yield payload, None
        continue

      # Some backends keep delivering YUYV frames even after toggling CONVERT_RGB.
      # Normalize to BGR before conversion to NV12.
      if frame.ndim == 3 and frame.shape[2] == 2:
        frame = cv.cvtColor(frame, cv.COLOR_YUV2BGR_YUY2)
      elif frame.ndim == 2:
        frame = cv.cvtColor(frame, cv.COLOR_GRAY2BGR)

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
