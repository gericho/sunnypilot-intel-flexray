#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, "/home/gericho/sunnypilot")
from opendbc.car.logreader import LogReader


def resolve_rlog(route: str) -> Path:
  p = Path(route)
  if p.is_file():
    return p
  rlog = p / "rlog.zst"
  if rlog.exists():
    return rlog
  raise FileNotFoundError(route)


def load_reference(csv_path: Path, feature: str, smooth_window: int) -> tuple[np.ndarray, np.ndarray]:
  ts: list[float] = []
  vals: list[float] = []
  with csv_path.open() as f:
    r = csv.DictReader(f)
    for row in r:
      raw = row.get(feature, "")
      if raw in ("", "None", None):
        continue
      try:
        v = float(raw)
        t = float(row["t_sec"])
      except ValueError:
        continue
      if math.isnan(v):
        continue
      ts.append(t)
      vals.append(v)

  if not ts:
    raise RuntimeError(f"no valid reference samples for {feature} in {csv_path}")

  t_arr = np.asarray(ts, dtype=np.float64)
  v_arr = np.asarray(vals, dtype=np.float64)
  if smooth_window > 1:
    pad = smooth_window // 2
    padded = np.pad(v_arr, (pad, pad), mode="edge")
    kernel = np.ones(smooth_window, dtype=np.float64) / smooth_window
    v_arr = np.convolve(padded, kernel, mode="valid")
  return t_arr, v_arr


def load_can_candidates(rlog_path: Path) -> dict[tuple[int, int, int], tuple[np.ndarray, np.ndarray]]:
  grouped: dict[tuple[int, int, int], list[tuple[float, bytes]]] = defaultdict(list)
  first_ts = None

  for evt in LogReader(str(rlog_path), only_union_types=True):
    if evt.which() != "can":
      continue
    ts = evt.logMonoTime / 1e9
    if first_ts is None:
      first_ts = ts
    rel = ts - first_ts
    for m in evt.can:
      dat = bytes(m.dat)
      grouped[(m.src, m.address, len(dat))].append((rel, dat))

  out = {}
  for key, rows in grouped.items():
    times = np.asarray([r[0] for r in rows], dtype=np.float64)
    payloads = np.asarray([list(r[1]) for r in rows], dtype=np.uint8)
    out[key] = (times, payloads)
  return out


def decode_fields(payloads: np.ndarray) -> list[tuple[str, np.ndarray]]:
  out: list[tuple[str, np.ndarray]] = []
  length = payloads.shape[1]
  for off in range(length):
    u8 = payloads[:, off].astype(np.float64)
    s8 = payloads[:, off].astype(np.int8).astype(np.float64)
    out.append((f"u8@{off}", u8))
    out.append((f"s8@{off}", s8))
  for off in range(length - 1):
    lo = payloads[:, off].astype(np.uint16)
    hi = payloads[:, off + 1].astype(np.uint16)
    u16 = (lo | (hi << 8)).astype(np.uint16).astype(np.float64)
    s16 = u16.astype(np.uint16).view(np.int16).astype(np.float64)
    out.append((f"u16le@{off}", u16))
    out.append((f"s16le@{off}", s16))
  return out


def held_interp(sample_t: np.ndarray, sample_v: np.ndarray, query_t: np.ndarray) -> np.ndarray:
  idx = np.searchsorted(sample_t, query_t, side="right") - 1
  out = np.full(query_t.shape, np.nan, dtype=np.float64)
  valid = idx >= 0
  if np.any(valid):
    out[valid] = sample_v[idx[valid]]
  return out


def pearson(a: np.ndarray, b: np.ndarray) -> float:
  mask = np.isfinite(a) & np.isfinite(b)
  if mask.sum() < 8:
    return float("nan")
  aa = a[mask]
  bb = b[mask]
  if np.allclose(aa, aa[0]) or np.allclose(bb, bb[0]):
    return float("nan")
  return float(np.corrcoef(aa, bb)[0, 1])


def rankdata(x: np.ndarray) -> np.ndarray:
  order = np.argsort(x, kind="mergesort")
  ranks = np.empty_like(order, dtype=np.float64)
  ranks[order] = np.arange(len(x), dtype=np.float64)
  return ranks


def spearman(a: np.ndarray, b: np.ndarray) -> float:
  mask = np.isfinite(a) & np.isfinite(b)
  if mask.sum() < 8:
    return float("nan")
  aa = a[mask]
  bb = b[mask]
  if np.allclose(aa, aa[0]) or np.allclose(bb, bb[0]):
    return float("nan")
  return pearson(rankdata(aa), rankdata(bb))


def best_lag_metrics(
  ref_t: np.ndarray,
  ref_v: np.ndarray,
  sample_t: np.ndarray,
  sample_v: np.ndarray,
  lags: np.ndarray,
) -> tuple[float, float, float, int, float, float]:
  best_abs = -1.0
  best_corr = float("nan")
  best_spear = float("nan")
  best_lag = 0.0
  best_n = 0
  best_std = float("nan")

  for lag in lags:
    aligned = held_interp(sample_t, sample_v, ref_t - lag)
    mask = np.isfinite(aligned) & np.isfinite(ref_v)
    n = int(mask.sum())
    if n < 8:
      continue
    corr = pearson(aligned, ref_v)
    if math.isnan(corr):
      continue
    score = abs(corr)
    if score > best_abs:
      best_abs = score
      best_corr = corr
      best_spear = spearman(aligned, ref_v)
      best_lag = float(lag)
      best_n = n
      best_std = float(np.nanstd(aligned[mask]))

  uniq = int(len(np.unique(sample_v)))
  return best_corr, best_spear, best_lag, best_n, best_std, float(uniq)


def write_csv(rows: list[dict], out_path: Path) -> None:
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with out_path.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(
      f,
      fieldnames=[
        "src", "address", "length", "field",
        "corr", "spearman", "lag_s", "n_aligned", "std", "uniq",
      ],
    )
    w.writeheader()
    for row in rows:
      w.writerow(row)


def main() -> int:
  ap = argparse.ArgumentParser(description="Scan raw CAN/FlexRay payload fields against a video steering proxy")
  ap.add_argument("route", help="route dir or rlog.zst")
  ap.add_argument("--ref-csv", default="/home/gericho/sunnypilot/tmp/route4_ecamera_steer_5fps.csv")
  ap.add_argument("--feature", default="spoke_rel_deg")
  ap.add_argument("--smooth-window", type=int, default=5)
  ap.add_argument("--lag-start", type=float, default=-1.0)
  ap.add_argument("--lag-end", type=float, default=1.0)
  ap.add_argument("--lag-step", type=float, default=0.1)
  ap.add_argument("--top", type=int, default=40)
  ap.add_argument("--min-uniq", type=int, default=8)
  ap.add_argument("--out-csv", default="/home/gericho/sunnypilot/tmp/bmw_i3_raw_signal_scan.csv")
  args = ap.parse_args()

  ref_t, ref_v = load_reference(Path(args.ref_csv), args.feature, args.smooth_window)
  lags = np.arange(args.lag_start, args.lag_end + 0.5 * args.lag_step, args.lag_step, dtype=np.float64)
  candidates = load_can_candidates(resolve_rlog(args.route))

  rows: list[dict] = []
  for (src, address, length), (sample_t, payloads) in candidates.items():
    for field_name, sample_v in decode_fields(payloads):
      corr, spear, lag_s, n_aligned, std, uniq = best_lag_metrics(ref_t, ref_v, sample_t, sample_v, lags)
      if math.isnan(corr) or uniq < args.min_uniq:
        continue
      rows.append({
        "src": src,
        "address": address,
        "length": length,
        "field": field_name,
        "corr": f"{corr:.6f}",
        "spearman": f"{spear:.6f}" if not math.isnan(spear) else "",
        "lag_s": f"{lag_s:.3f}",
        "n_aligned": n_aligned,
        "std": f"{std:.6f}" if not math.isnan(std) else "",
        "uniq": int(uniq),
      })

  rows.sort(key=lambda r: abs(float(r["corr"])), reverse=True)
  write_csv(rows, Path(args.out_csv))

  print(f"reference_feature={args.feature}")
  print(f"reference_samples={len(ref_t)}")
  print(f"wrote_csv={args.out_csv}")
  for row in rows[:args.top]:
    print(
      f"src={row['src']} addr={row['address']} len={row['length']} field={row['field']} "
      f"corr={row['corr']} spearman={row['spearman']} lag={row['lag_s']} "
      f"uniq={row['uniq']} std={row['std']}"
    )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
