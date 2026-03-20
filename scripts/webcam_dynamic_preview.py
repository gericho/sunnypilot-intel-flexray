#!/usr/bin/env python3
import argparse
import os
import sys

import cv2 as cv
import numpy as np

from openpilot.tools.webcam.camera import Camera


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--stdout", action="store_true", help="Write BGR24 raw video to stdout instead of opening a window")
  args = parser.parse_args()

  os.environ.setdefault("ROAD_CAM", "/dev/video0")
  os.environ.setdefault("ROAD_W", "1280")
  os.environ.setdefault("ROAD_H", "720")
  os.environ.setdefault("ROAD_FPS", "20")
  os.environ.setdefault("ROAD_FOURCC", "MJPG")
  os.environ.setdefault("WEBCAM_BACKEND", "ffmpeg")
  os.environ.setdefault("WEBCAM_FLIP", "-1")
  os.environ.setdefault("WEBCAM_DYNAMIC_EXPOSURE", "1")

  raw_out = None
  if args.stdout:
    raw_out = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    sys.stdout = sys.stderr

  cam = Camera("roadCameraState", None, os.environ["ROAD_CAM"])
  h = int(cam.H)
  w = int(cam.W)

  try:
    for payload, _stage in cam.read_frames():
      frame = np.frombuffer(payload, dtype=np.uint8).reshape((h * 3 // 2, w))
      bgr = cv.cvtColor(frame, cv.COLOR_YUV2BGR_NV12)
      if args.stdout:
        raw_out.write(bgr.tobytes())
        raw_out.flush()
      else:
        cv.imshow("webcam_dynamic_preview", bgr)
        key = cv.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
          break
  finally:
    if not args.stdout:
      cv.destroyAllWindows()


if __name__ == "__main__":
  main()
