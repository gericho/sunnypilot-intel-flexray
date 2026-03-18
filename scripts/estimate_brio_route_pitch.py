#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import math
import os
from dataclasses import dataclass
from statistics import median

import cv2
import numpy as np


@dataclass
class Estimate:
  file: str
  vp_x: float
  vp_y: float
  pitch_rad: float
  left_n: int
  right_n: int


def focal_from_hfov(width: int, hfov_deg: float) -> float:
  return (width / 2.0) / math.tan(math.radians(hfov_deg / 2.0))


def fit_side_line(lines: list[tuple[float, float, float, float]]) -> tuple[float, float] | None:
  if not lines:
    return None
  xs = []
  ys = []
  ws = []
  for x1, y1, x2, y2 in lines:
    length = math.hypot(x2 - x1, y2 - y1)
    xs.extend([x1, x2])
    ys.extend([y1, y2])
    ws.extend([length, length])
  coeffs = np.polyfit(xs, ys, 1, w=np.array(ws))
  m, b = float(coeffs[0]), float(coeffs[1])
  return m, b


def intersect(line_a: tuple[float, float], line_b: tuple[float, float]) -> tuple[float, float] | None:
  ma, ba = line_a
  mb, bb = line_b
  if abs(ma - mb) < 1e-6:
    return None
  x = (bb - ba) / (ma - mb)
  y = ma * x + ba
  return float(x), float(y)


def estimate_from_image(path: str, hfov_deg: float = 60.0) -> Estimate | None:
  img = cv2.imread(path)
  if img is None:
    return None

  h, w = img.shape[:2]
  gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
  blur = cv2.GaussianBlur(gray, (5, 5), 0)
  edges = cv2.Canny(blur, 50, 150)

  mask = np.zeros_like(edges)
  roi = np.array([[
    (0, h),
    (0, int(h * 0.45)),
    (w, int(h * 0.45)),
    (w, h),
  ]], dtype=np.int32)
  cv2.fillPoly(mask, roi, 255)
  edges = cv2.bitwise_and(edges, mask)

  raw = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30, minLineLength=25, maxLineGap=20)
  if raw is None:
    return None

  left: list[tuple[float, float, float, float]] = []
  right: list[tuple[float, float, float, float]] = []
  cx = w / 2.0

  for r in raw[:, 0, :]:
    x1, y1, x2, y2 = map(float, r)
    if abs(x2 - x1) < 1.0:
      continue
    slope = (y2 - y1) / (x2 - x1)
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 30:
      continue
    if abs(slope) < 0.25 or abs(slope) > 4.5:
      continue

    midx = 0.5 * (x1 + x2)
    if slope < 0 and midx < cx:
      left.append((x1, y1, x2, y2))
    elif slope > 0 and midx > cx:
      right.append((x1, y1, x2, y2))

  if len(left) < 2 or len(right) < 2:
    return None

  lfit = fit_side_line(left)
  rfit = fit_side_line(right)
  if lfit is None or rfit is None:
    return None

  vp = intersect(lfit, rfit)
  if vp is None:
    return None
  vp_x, vp_y = vp
  if not (0 <= vp_x <= w and -h <= vp_y <= h):
    return None

  fx = focal_from_hfov(w, hfov_deg)
  fy = fx
  cy = h / 2.0
  pitch_rad = math.atan2(cy - vp_y, fy)
  return Estimate(
    file=os.path.basename(path),
    vp_x=vp_x,
    vp_y=vp_y,
    pitch_rad=pitch_rad,
    left_n=len(left),
    right_n=len(right),
  )


def main() -> int:
  ap = argparse.ArgumentParser(description="Estimate BRIO road pitch from extracted route frames")
  ap.add_argument("pattern", nargs="?", default="/home/gericho/sunnypilot/captures/00000179_fcamera_frames/*.jpg")
  ap.add_argument("--hfov", type=float, default=60.0)
  args = ap.parse_args()

  files = sorted(glob.glob(args.pattern))
  print(f"files {len(files)} hfov_deg={args.hfov}")
  ests = [e for e in (estimate_from_image(f, args.hfov) for f in files) if e is not None]
  print(f"usable {len(ests)}")
  if not ests:
    return 1

  pitch_rads = [e.pitch_rad for e in ests]
  pitch_degs = [math.degrees(p) for p in pitch_rads]
  vp_ys = [e.vp_y for e in ests]
  vp_xs = [e.vp_x for e in ests]

  print("summary", {
    "median_pitch_rad": round(float(median(pitch_rads)), 6),
    "median_pitch_deg": round(float(median(pitch_degs)), 4),
    "median_vp_y": round(float(median(vp_ys)), 2),
    "median_vp_x": round(float(median(vp_xs)), 2),
    "min_pitch_deg": round(float(min(pitch_degs)), 4),
    "max_pitch_deg": round(float(max(pitch_degs)), 4),
  })
  print("samples")
  for e in ests[:12]:
    print({
      "file": e.file,
      "vp_x": round(e.vp_x, 2),
      "vp_y": round(e.vp_y, 2),
      "pitch_deg": round(math.degrees(e.pitch_rad), 4),
      "left_n": e.left_n,
      "right_n": e.right_n,
    })
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
