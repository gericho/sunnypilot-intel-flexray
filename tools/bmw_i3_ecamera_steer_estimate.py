#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

import sys
sys.path.insert(0, "/home/gericho/sunnypilot")
from tools.check_route_video_timing import video_stats


def resolve_route_segments(route: str) -> list[Path]:
  p = Path(route)
  if p.is_file():
    if p.name == "ecamera.hevc":
      return [p]
    raise FileNotFoundError(f"unsupported file path: {p}")

  if "--" in p.name and p.name.rsplit("--", 1)[-1].isdigit():
    stem = p.name.rsplit("--", 1)[0] + "--"
    base = p.parent
  else:
    stem = p.name
    base = p.parent

  segs = sorted(base.glob(f"{stem}[0-9]*"))
  out = [seg / "ecamera.hevc" for seg in segs if (seg / "ecamera.hevc").exists()]
  if not out:
    raise FileNotFoundError(f"no ecamera segments found for {route}")
  return out


def build_mask(shape: tuple[int, int], cx: int, cy: int, radius: int) -> np.ndarray:
  mask = np.zeros(shape, dtype=np.uint8)
  cv2.circle(mask, (cx, cy), radius, 255, -1)
  return mask


def spoke_angle(gray: np.ndarray, mask: np.ndarray) -> float | None:
  blur = cv2.GaussianBlur(gray, (5, 5), 0)
  edges = cv2.Canny(blur, 60, 140)
  edges = cv2.bitwise_and(edges, mask)
  lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=25, minLineLength=35, maxLineGap=8)
  if lines is None:
    return None

  angles: list[float] = []
  for l in lines[:, 0, :]:
    x1, y1, x2, y2 = l
    ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
    while ang >= 90:
      ang -= 180
    while ang < -90:
      ang += 180
    length = math.hypot(x2 - x1, y2 - y1)
    if abs(ang) < 80:
      angles.extend([ang] * max(1, int(length)))
  if not angles:
    return None
  return float(np.median(angles))


def ecc_rotation(ref: np.ndarray, img: np.ndarray, mask: np.ndarray) -> tuple[float | None, float | None]:
  warp = np.eye(2, 3, dtype=np.float32)
  try:
    cc, warp = cv2.findTransformECC(
      ref,
      img,
      warp,
      cv2.MOTION_EUCLIDEAN,
      criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5),
      inputMask=mask,
      gaussFiltSize=5,
    )
  except cv2.error:
    return None, None
  ang = math.degrees(math.atan2(warp[1, 0], warp[0, 0]))
  return ang, float(cc)


def sample_route(
  segments: Iterable[Path],
  fps: float,
  video_fps: float,
  roi: tuple[int, int, int, int],
  circle: tuple[int, int, int],
) -> list[dict]:
  x, y, w, h = roi
  cx, cy, radius = circle
  mask = build_mask((h, w), cx, cy, radius)
  inner_mask = build_mask((h, w), cx, cy, max(10, radius - 35))

  rows: list[dict] = []
  seg_offset = 0.0
  ref_gray = None
  ref_spoke = None

  for seg in segments:
    stride = max(1, int(round(video_fps / fps)))
    cap = cv2.VideoCapture(str(seg))
    if not cap.isOpened():
      raise RuntimeError(f"failed opening {seg}")
    frame_idx = 0
    while True:
      ok, frame = cap.read()
      if not ok:
        break
      idx = frame_idx
      frame_idx += 1
      if idx % stride != 0:
        continue
      gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
      crop = gray[y:y + h, x:x + w]
      crop_eq = cv2.equalizeHist(crop)
      if ref_gray is None:
        ref_gray = crop_eq.copy()
        ref_spoke = spoke_angle(crop_eq, inner_mask)

      ecc_deg, ecc_cc = ecc_rotation(ref_gray, crop_eq, mask)
      spoke_deg = spoke_angle(crop_eq, inner_mask)
      if spoke_deg is not None and ref_spoke is not None:
        spoke_rel = spoke_deg - ref_spoke
      else:
        spoke_rel = None

      rows.append({
        "segment": seg.parent.name,
        "frame_idx": idx,
        "t_sec": seg_offset + (idx / video_fps),
        "ecc_deg": ecc_deg,
        "ecc_cc": ecc_cc,
        "spoke_deg": spoke_deg,
        "spoke_rel_deg": spoke_rel,
      })
    cap.release()
    seg_offset += frame_idx / video_fps
  return rows


def write_csv(rows: list[dict], out_csv: Path) -> None:
  out_csv.parent.mkdir(parents=True, exist_ok=True)
  with out_csv.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["segment", "frame_idx", "t_sec", "ecc_deg", "ecc_cc", "spoke_deg", "spoke_rel_deg"])
    w.writeheader()
    for row in rows:
      w.writerow(row)


def write_preview(seg: Path, out_path: Path, roi: tuple[int, int, int, int], circle: tuple[int, int, int]) -> None:
  cap = cv2.VideoCapture(str(seg))
  ok, bgr = cap.read()
  cap.release()
  if not ok:
    raise RuntimeError(f"failed opening {seg}")
  x, y, w, h = roi
  cx, cy, radius = circle
  cv2.rectangle(bgr, (x, y), (x + w, y + h), (0, 255, 255), 2)
  cv2.circle(bgr, (x + cx, y + cy), radius, (0, 255, 0), 2)
  out_path.parent.mkdir(parents=True, exist_ok=True)
  cv2.imwrite(str(out_path), bgr)


def main() -> int:
  ap = argparse.ArgumentParser(description="Estimate BMW i3 steering wheel rotation from ecamera HEVC only")
  ap.add_argument("route", help="route stem or segment dir")
  ap.add_argument("--fps", type=int, default=5, help="sampling FPS from 20 fps source")
  ap.add_argument("--video-fps", type=float, default=None, help="override real source fps; defaults to packet cadence")
  ap.add_argument("--roi", default="250,0,330,320", help="x,y,w,h crop in full ecamera frame")
  ap.add_argument("--circle", default="160,155,125", help="cx,cy,r inside ROI")
  ap.add_argument("--out-csv", default="/home/gericho/sunnypilot/tmp/ecamera_steer_estimate.csv")
  ap.add_argument("--out-preview", default="/home/gericho/sunnypilot/tmp/ecamera_steer_estimate_preview.jpg")
  args = ap.parse_args()

  roi = tuple(int(v) for v in args.roi.split(","))
  circle = tuple(int(v) for v in args.circle.split(","))
  if len(roi) != 4 or len(circle) != 3:
    raise ValueError("invalid roi/circle format")

  segments = resolve_route_segments(args.route)
  inferred_video_fps = args.video_fps
  if inferred_video_fps is None:
    stats = video_stats(segments[0])
    pkt = stats.get("packet_duration_s")
    if not pkt:
      raise RuntimeError(f"failed to infer packet cadence from {segments[0]}")
    inferred_video_fps = 1.0 / pkt

  rows = sample_route(segments, args.fps, inferred_video_fps, roi, circle)
  write_csv(rows, Path(args.out_csv))
  write_preview(segments[0], Path(args.out_preview), roi, circle)

  valid_ecc = sum(1 for r in rows if r["ecc_deg"] is not None)
  valid_spoke = sum(1 for r in rows if r["spoke_rel_deg"] is not None)
  print(f"segments={len(segments)} video_fps={inferred_video_fps:.3f} samples={len(rows)} valid_ecc={valid_ecc} valid_spoke={valid_spoke}")
  print(f"csv={args.out_csv}")
  print(f"preview={args.out_preview}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
