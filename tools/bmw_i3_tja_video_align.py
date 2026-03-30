#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2
import numpy as np

import sys
sys.path.insert(0, '/home/gericho/sunnypilot')
from opendbc.car.logreader import LogReader
from tools.check_route_video_timing import video_stats


def resolve_segments(route: str, filename: str) -> list[Path]:
  p = Path(route)
  if p.is_file():
    if p.name == filename:
      return [p]
    raise FileNotFoundError(p)
  if '--' in p.name and p.name.rsplit('--', 1)[-1].isdigit():
    stem = p.name.rsplit('--', 1)[0] + '--'
    base = p.parent
  else:
    stem = p.name
    base = p.parent
  segs = sorted(base.glob(f'{stem}[0-9]*'))
  out = [seg / filename for seg in segs if (seg / filename).exists()]
  if not out:
    raise FileNotFoundError(f'no {filename} segments for {route}')
  return out


def u16le(b: bytes, off: int) -> int:
  return b[off] | (b[off + 1] << 8)


def load_rlog_lateral(route: str) -> list[dict]:
  rows = []
  seg_offset = 0.0
  for rlog in resolve_segments(route, 'rlog.zst'):
    first_ts = None
    last = {72: None, 96: None, 131: None, 135: None}
    for evt in LogReader(str(rlog), only_union_types=True):
      if evt.which() != 'can':
        continue
      ts = evt.logMonoTime / 1e9
      if first_ts is None:
        first_ts = ts
      rel = seg_offset + (ts - first_ts)
      touched = False
      for m in evt.can:
        dat = bytes(m.dat)
        if (m.src, m.address) == (0, 72) and len(dat) >= 9:
          last[72] = dat
          touched = True
        elif (m.src, m.address) == (0, 96) and len(dat) >= 9:
          last[96] = dat
          touched = True
        elif (m.src, m.address) == (0, 131) and len(dat) >= 9:
          last[131] = dat
          touched = True
        elif (m.src, m.address) == (0, 135) and len(dat) >= 9:
          last[135] = dat
          touched = True
      if touched and all(last.values()):
        gate = u16le(last[131], 5)
        state = u16le(last[135], 5)
        rows.append({
          't_sec': rel,
          'phase72': last[72][0],
          'cnt72': last[72][2] & 0x0F,
          'b1': last[96][1],
          'b2': last[96][2],
          'gate131': gate,
          'state135': state,
          'tail135': last[135][3:9].hex(),
          'tja_state': gate == 640 and state == 24802 and last[135][3:9].hex() == '2228e2604206',
        })
    if rows:
      seg_offset = rows[-1]['t_sec']
  return rows


def find_tja_window(rows: list[dict]) -> tuple[float, float]:
  active = [r['t_sec'] for r in rows if r['tja_state']]
  if not active:
    raise RuntimeError('no clean TJA window found in rlog')
  return min(active), max(active)


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
      criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 150, 1e-5),
      inputMask=mask,
      gaussFiltSize=5,
    )
  except cv2.error:
    return None, None
  ang = math.degrees(math.atan2(warp[1, 0], warp[0, 0]))
  return ang, float(cc)


def pairwise_rotation(prev: np.ndarray, cur: np.ndarray, mask: np.ndarray) -> tuple[float | None, int, int]:
  pts0 = cv2.goodFeaturesToTrack(
    prev,
    maxCorners=250,
    qualityLevel=0.01,
    minDistance=6,
    blockSize=7,
    mask=mask,
  )
  if pts0 is None or len(pts0) < 8:
    return None, 0, 0

  pts1, st, _err = cv2.calcOpticalFlowPyrLK(
    prev,
    cur,
    pts0,
    None,
    winSize=(21, 21),
    maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
  )
  if pts1 is None or st is None:
    return None, int(len(pts0)), 0

  good0 = pts0[st[:, 0] == 1]
  good1 = pts1[st[:, 0] == 1]
  if len(good0) < 8:
    return None, int(len(pts0)), int(len(good0))

  mat, inliers = cv2.estimateAffinePartial2D(
    good0.reshape(-1, 2),
    good1.reshape(-1, 2),
    method=cv2.RANSAC,
    ransacReprojThreshold=2.5,
    maxIters=2000,
    confidence=0.99,
    refineIters=10,
  )
  if mat is None:
    return None, int(len(pts0)), int(len(good0))

  ang = math.degrees(math.atan2(mat[1, 0], mat[0, 0]))
  if abs(ang) > 8.0:
    return None, int(len(pts0)), int(inliers.sum()) if inliers is not None else int(len(good0))
  return ang, int(len(pts0)), int(inliers.sum()) if inliers is not None else int(len(good0))


def build_feature_mask(shape: tuple[int, int], cx: int, cy: int, radius: int) -> np.ndarray:
  h, w = shape
  yy, xx = np.mgrid[0:h, 0:w]
  dx = xx - cx
  dy = cy - yy
  rr = np.sqrt(dx * dx + (yy - cy) * (yy - cy))
  ang = np.degrees(np.arctan2(dy, dx))

  # Keep the steering-wheel spokes and upper ring, drop the lower hand-occluded arc.
  annulus = (rr >= max(28, radius - 92)) & (rr <= max(35, radius - 8))
  not_lower_arc = ~((ang >= -150.0) & (ang <= -30.0))
  mask = np.where(annulus & not_lower_arc, 255, 0).astype(np.uint8)
  return mask


def analyze_video(route: str, start_t: float, end_t: float, fps_out: float, video_fps: float, roi: tuple[int, int, int, int], circle: tuple[int, int, int]) -> list[dict]:
  x, y, w, h = roi
  cx, cy, radius = circle
  mask = np.zeros((h, w), dtype=np.uint8)
  cv2.circle(mask, (cx, cy), radius, 255, -1)
  inner_mask = np.zeros((h, w), dtype=np.uint8)
  cv2.circle(inner_mask, (cx, cy), max(10, radius - 35), 255, -1)
  feature_mask = build_feature_mask((h, w), cx, cy, radius)

  rows = []
  seg_offset = 0.0
  ref = None
  ref_spoke = None
  prev_crop = None
  pairwise_cum = 0.0
  sample_step = max(1, int(round(video_fps / fps_out)))

  for seg in resolve_segments(route, 'ecamera.hevc'):
    cap = cv2.VideoCapture(str(seg))
    if not cap.isOpened():
      raise RuntimeError(f'failed opening {seg}')
    frame_idx = 0
    while True:
      ok, frame = cap.read()
      if not ok:
        break
      rel_t = seg_offset + frame_idx / video_fps
      if rel_t > end_t:
        break
      if rel_t >= start_t and frame_idx % sample_step == 0:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        crop = gray[y:y + h, x:x + w]
        crop_eq = cv2.equalizeHist(crop)
        if ref is None:
          ref = crop_eq.copy()
          ref_spoke = spoke_angle(crop_eq, inner_mask)
        ecc_deg, ecc_cc = ecc_rotation(ref, crop_eq, mask)
        pairwise_deg = None
        pairwise_pts = 0
        pairwise_inliers = 0
        if prev_crop is not None:
          pairwise_deg, pairwise_pts, pairwise_inliers = pairwise_rotation(prev_crop, crop_eq, feature_mask)
          if pairwise_deg is not None:
            pairwise_cum += pairwise_deg
        spoke_deg = spoke_angle(crop_eq, inner_mask)
        spoke_rel = None if spoke_deg is None or ref_spoke is None else (spoke_deg - ref_spoke)
        rows.append({
          't_sec': rel_t,
          'frame_idx': frame_idx,
          'ecc_deg': ecc_deg,
          'ecc_cc': ecc_cc,
          'pairwise_deg': pairwise_deg,
          'pairwise_cum_deg': pairwise_cum,
          'pairwise_pts': pairwise_pts,
          'pairwise_inliers': pairwise_inliers,
          'spoke_deg': spoke_deg,
          'spoke_rel_deg': spoke_rel,
        })
        prev_crop = crop_eq
      frame_idx += 1
    cap.release()
    seg_offset += frame_idx / video_fps
  return rows


def infer_video_fps(route: str) -> float:
  segs = resolve_segments(route, 'ecamera.hevc')
  stats = video_stats(segs[0])
  pkt = stats.get("packet_duration_s")
  if not pkt:
    raise RuntimeError(f"failed to infer video fps from {segs[0]}")
  return 1.0 / pkt


def nearest_rlog(rows: list[dict], t: float) -> dict | None:
  if not rows:
    return None
  return min(rows, key=lambda r: abs(r['t_sec'] - t))


def write_csv(path: Path, rows: list[dict], rlog_rows: list[dict]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['t_sec', 'frame_idx', 'ecc_deg', 'ecc_cc', 'pairwise_deg', 'pairwise_cum_deg', 'pairwise_pts', 'pairwise_inliers', 'spoke_deg', 'spoke_rel_deg', 'phase72', 'b1', 'b2', 'gate131', 'state135', 'tail135', 'tja_state'])
    for row in rows:
      rr = nearest_rlog(rlog_rows, row['t_sec'])
      w.writerow([
        f"{row['t_sec']:.3f}", row['frame_idx'], row['ecc_deg'], row['ecc_cc'], row['pairwise_deg'], row['pairwise_cum_deg'], row['pairwise_pts'], row['pairwise_inliers'], row['spoke_deg'], row['spoke_rel_deg'],
        rr['phase72'] if rr else '', rr['b1'] if rr else '', rr['b2'] if rr else '', rr['gate131'] if rr else '', rr['state135'] if rr else '', rr['tail135'] if rr else '', rr['tja_state'] if rr else ''
      ])


def main() -> int:
  ap = argparse.ArgumentParser(description='Analyze full ecamera TJA segment and align to rlog lateral events')
  ap.add_argument('route', help='route stem or segment dir')
  ap.add_argument('--fps', type=float, default=2.0)
  ap.add_argument('--video-fps', type=float, default=None)
  ap.add_argument('--roi', default='250,0,330,320')
  ap.add_argument('--circle', default='160,155,125')
  ap.add_argument('--pad-start', type=float, default=0.0)
  ap.add_argument('--pad-end', type=float, default=0.0)
  ap.add_argument('--out-csv', default='/home/gericho/sunnypilot/tmp/tja_ecamera_aligned.csv')
  args = ap.parse_args()

  roi = tuple(int(v) for v in args.roi.split(','))
  circle = tuple(int(v) for v in args.circle.split(','))
  rlog_rows = load_rlog_lateral(args.route)
  t_start, t_end = find_tja_window(rlog_rows)
  t_start = max(0.0, t_start - args.pad_start)
  t_end = t_end + args.pad_end
  video_fps = args.video_fps if args.video_fps is not None else infer_video_fps(args.route)
  video_rows = analyze_video(args.route, t_start, t_end, args.fps, video_fps, roi, circle)
  write_csv(Path(args.out_csv), video_rows, rlog_rows)
  print(f'tja_window={t_start:.3f}..{t_end:.3f}')
  print(f'samples={len(video_rows)}')
  print(f'video_fps={video_fps:.3f}')
  print(f'csv={args.out_csv}')
  return 0

if __name__ == '__main__':
  raise SystemExit(main())
