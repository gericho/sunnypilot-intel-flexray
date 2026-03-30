#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, "/home/gericho/sunnypilot")
from opendbc.car.logreader import LogReader


def u16le(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


def scale_770(raw: int) -> float:
  return raw * 0.04375 - 1433.6


def iter_windowed_updates(segments: list[tuple[Path, float, float]]):
  route_offset = 0.0
  updates: list[dict] = []
  track: list[tuple[float, float]] = []

  for path, win_s, win_e in segments:
    first = None
    last72 = None
    last264 = None
    ang770 = None

    for evt in LogReader(str(path), only_union_types=True):
      if evt.which() != "can":
        continue
      ts = evt.logMonoTime / 1e9
      if first is None:
        first = ts
      rel = ts - first

      if rel < win_s:
        for m in evt.can:
          dat = bytes(m.dat)
          if m.src == 0 and m.address == 72 and len(dat) >= 9:
            last72 = dat
          elif m.src == 0 and m.address == 264 and len(dat) >= 3:
            last264 = dat
          elif m.src == 2 and m.address == 770 and len(dat) >= 4:
            ang770 = scale_770(u16le(dat, 2))
        continue

      if rel > win_e:
        break

      t_route = route_offset + rel
      for m in evt.can:
        dat = bytes(m.dat)
        if m.src == 0 and m.address == 72 and len(dat) >= 9:
          last72 = dat
        elif m.src == 0 and m.address == 264 and len(dat) >= 3:
          last264 = dat
        elif m.src == 2 and m.address == 770 and len(dat) >= 4:
          ang770 = scale_770(u16le(dat, 2))
          track.append((t_route, ang770))
        elif m.src == 0 and m.address == 96 and len(dat) >= 5 and last72 is not None and ang770 is not None:
          updates.append({
            "t": t_route,
            "phase72": last72[0],
            "cnt72": last72[2] & 0x0F,
            "b0_96": dat[0],
            "b1_96": dat[1],
            "b2_96": dat[2],
            "b3_96": dat[3],
            "b4_96": dat[4],
            "b1_264": None if last264 is None else last264[1],
            "ang0_770": ang770,
          })

    if track:
      route_offset = track[-1][0]

  return updates, track


def held_value(ts: list[float], vals: list[float], query_t: float) -> float | None:
  idx = bisect.bisect_right(ts, query_t) - 1
  return vals[idx] if idx >= 0 else None


def enrich_deltas(updates: list[dict], track: list[tuple[float, float]], horizons: list[float]) -> None:
  ts = [t for t, _ in track]
  vals = [v for _, v in track]
  for u in updates:
    for horizon in horizons:
      key = f"d{int(round(horizon * 1000)):03d}"
      v = held_value(ts, vals, u["t"] + horizon)
      u[key] = None if v is None else v - u["ang0_770"]


def fit_linear_per_phase(updates: list[dict], target_key: str, min_samples: int) -> list[dict]:
  grouped: dict[int, list[dict]] = defaultdict(list)
  for u in updates:
    grouped[u["phase72"]].append(u)

  out: list[dict] = []
  for phase, vals in grouped.items():
    rows = [v for v in vals if v[target_key] is not None]
    if len(rows) < min_samples:
      continue

    X = np.asarray([[1.0, v["b1_96"], v["b2_96"]] for v in rows], dtype=np.float64)
    y = np.asarray([v[target_key] for v in rows], dtype=np.float64)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = None if ss_tot < 1e-9 else 1.0 - ss_res / ss_tot
    corr = None
    if len(set(np.round(pred, 9))) > 1 and len(set(np.round(y, 9))) > 1:
      corr = float(np.corrcoef(pred, y)[0, 1])

    out.append({
      "phase72": phase,
      "n": len(rows),
      "b1min": min(v["b1_96"] for v in rows),
      "b1max": max(v["b1_96"] for v in rows),
      "b2min": min(v["b2_96"] for v in rows),
      "b2max": max(v["b2_96"] for v in rows),
      "avg_target": float(y.mean()),
      "r2": r2,
      "corr_pred": corr,
      "bias": float(coef[0]),
      "k_b1": float(coef[1]),
      "k_b2": float(coef[2]),
    })
  out.sort(key=lambda r: abs(r["corr_pred"]) if r["corr_pred"] is not None else -1.0, reverse=True)
  return out


def fit_periodic_phase_model(rows: list[dict], value_key: str) -> dict | None:
  valid = [r for r in rows if r[value_key] is not None]
  if len(valid) < 4:
    return None
  phases = np.asarray([r["phase72"] for r in valid], dtype=np.float64)
  y = np.asarray([r[value_key] for r in valid], dtype=np.float64)
  ang = 2.0 * np.pi * phases / 64.0
  X = np.column_stack([np.ones(len(phases)), np.sin(ang), np.cos(ang), np.sin(2.0 * ang), np.cos(2.0 * ang)])
  coef, *_ = np.linalg.lstsq(X, y, rcond=None)
  pred = X @ coef
  ss_res = float(np.sum((y - pred) ** 2))
  ss_tot = float(np.sum((y - y.mean()) ** 2))
  r2 = None if ss_tot < 1e-9 else 1.0 - ss_res / ss_tot
  corr = None
  if len(set(np.round(pred, 9))) > 1 and len(set(np.round(y, 9))) > 1:
    corr = float(np.corrcoef(pred, y)[0, 1])
  return {
    "value_key": value_key,
    "corr_pred": corr,
    "r2": r2,
    "c0": float(coef[0]),
    "sin1": float(coef[1]),
    "cos1": float(coef[2]),
    "sin2": float(coef[3]),
    "cos2": float(coef[4]),
  }


def build_operational_rows(rows: list[dict], min_corr: float, min_r2: float, min_abs_avg: float) -> list[dict]:
  out: list[dict] = []
  for row in rows:
    corr = row["corr_pred"]
    r2 = row["r2"]
    avg = row["avg_target"]
    if corr is None or r2 is None:
      continue
    if abs(corr) < min_corr or r2 < min_r2 or abs(avg) < min_abs_avg:
      continue

    kb1 = row["k_b1"]
    kb2 = row["k_b2"]
    abs_kb1 = abs(kb1)
    abs_kb2 = abs(kb2)
    if abs_kb2 > abs_kb1 * 8.0:
      dominant = "b2"
    elif abs_kb1 > abs_kb2 * 1.2:
      dominant = "b1"
    else:
      dominant = "hybrid"

    out.append({
      "phase72": row["phase72"],
      "n": row["n"],
      "avg_target": avg,
      "corr_pred": corr,
      "r2": r2,
      "direction": "neg" if avg < 0.0 else "pos",
      "dominant": dominant,
      "bias": row["bias"],
      "k_b1": kb1,
      "k_b2": kb2,
      "b1min": row["b1min"],
      "b1max": row["b1max"],
      "b2min": row["b2min"],
      "b2max": row["b2max"],
    })
  out.sort(key=lambda r: abs(r["corr_pred"]), reverse=True)
  return out


def write_csv(rows: list[dict], out_path: Path) -> None:
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with out_path.open("w", newline="", encoding="utf-8") as f:
    fieldnames = [
      "phase72", "n", "b1min", "b1max", "b2min", "b2max",
      "avg_target", "r2", "corr_pred", "bias", "k_b1", "k_b2",
    ]
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for row in rows:
      w.writerow(row)


def write_operational_csv(rows: list[dict], out_path: Path) -> None:
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with out_path.open("w", newline="", encoding="utf-8") as f:
    fieldnames = [
      "phase72", "n", "direction", "dominant",
      "avg_target", "corr_pred", "r2",
      "bias", "k_b1", "k_b2",
      "b1min", "b1max", "b2min", "b2max",
    ]
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for row in rows:
      w.writerow(row)


def write_periodic_csv(rows: list[dict], out_path: Path) -> None:
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with out_path.open("w", newline="", encoding="utf-8") as f:
    fieldnames = ["value_key", "corr_pred", "r2", "c0", "sin1", "cos1", "sin2", "cos2"]
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for row in rows:
      w.writerow(row)


def main() -> int:
  ap = argparse.ArgumentParser(description="Fit phase-local 96->770 steering motion maps on the BMW i3 TJA route")
  ap.add_argument("--seg0", default="/home/gericho/Desktop/Backup routes/00000402--59a94efa08--0/rlog.zst")
  ap.add_argument("--seg1", default="/home/gericho/Desktop/Backup routes/00000402--59a94efa08--1/rlog.zst")
  ap.add_argument("--seg0-start", type=float, default=21.0)
  ap.add_argument("--seg0-end", type=float, default=72.2)
  ap.add_argument("--seg1-start", type=float, default=0.0)
  ap.add_argument("--seg1-end", type=float, default=48.5)
  ap.add_argument("--target-ms", type=int, default=600, choices=(200, 400, 600))
  ap.add_argument("--min-samples", type=int, default=8)
  ap.add_argument("--out-csv", default="")
  ap.add_argument("--operational-out", default="")
  ap.add_argument("--periodic-out", default="")
  ap.add_argument("--min-corr", type=float, default=0.43)
  ap.add_argument("--min-r2", type=float, default=0.18)
  ap.add_argument("--min-abs-avg", type=float, default=0.12)
  args = ap.parse_args()

  segments = [
    (Path(args.seg0), args.seg0_start, args.seg0_end),
    (Path(args.seg1), args.seg1_start, args.seg1_end),
  ]
  updates, track = iter_windowed_updates(segments)
  enrich_deltas(updates, track, [0.2, 0.4, 0.6])
  target_key = f"d{args.target_ms:03d}"
  rows = fit_linear_per_phase(updates, target_key, args.min_samples)
  operational_rows = build_operational_rows(rows, args.min_corr, args.min_r2, args.min_abs_avg)
  periodic_rows = [fit_periodic_phase_model(rows, "avg_target"), fit_periodic_phase_model(rows, "k_b1"), fit_periodic_phase_model(rows, "k_b2")]
  periodic_rows = [r for r in periodic_rows if r is not None]

  out_csv = Path(args.out_csv) if args.out_csv else Path(f"/home/gericho/sunnypilot/tmp/tja_402_phase_linear_fit_{target_key}.csv")
  operational_csv = Path(args.operational_out) if args.operational_out else Path(f"/home/gericho/sunnypilot/tmp/tja_402_phase_action_map_{target_key}.csv")
  periodic_csv = Path(args.periodic_out) if args.periodic_out else Path(f"/home/gericho/sunnypilot/tmp/tja_402_phase_periodic_summary_{target_key}.csv")
  write_csv(rows, out_csv)
  write_operational_csv(operational_rows, operational_csv)
  write_periodic_csv(periodic_rows, periodic_csv)

  print(f"updates={len(updates)} track={len(track)} target={target_key}")
  print(f"wrote_csv={out_csv}")
  print(f"wrote_operational_csv={operational_csv}")
  print(f"wrote_periodic_csv={periodic_csv}")
  for row in rows[:16]:
    print(
      f"phase={row['phase72']} n={row['n']} corr={'' if row['corr_pred'] is None else f'{row['corr_pred']:.3f}'} "
      f"r2={'' if row['r2'] is None else f'{row['r2']:.3f}'} avg={row['avg_target']:.3f} "
      f"bias={row['bias']:.4f} k_b1={row['k_b1']:.5f} k_b2={row['k_b2']:.5f}"
    )
  if operational_rows:
    print("operational_map")
    for row in operational_rows:
      print(
        f" phase={row['phase72']} dir={row['direction']} dom={row['dominant']} "
        f"corr={row['corr_pred']:.3f} r2={row['r2']:.3f} avg={row['avg_target']:.3f} "
        f"k_b1={row['k_b1']:.5f} k_b2={row['k_b2']:.5f}"
      )
  if periodic_rows:
    print("periodic_summary")
    for row in periodic_rows:
      print(
        f" {row['value_key']}: corr={'' if row['corr_pred'] is None else f'{row['corr_pred']:.3f}'} "
        f"r2={'' if row['r2'] is None else f'{row['r2']:.3f}'} "
        f"c0={row['c0']:.5f} sin1={row['sin1']:.5f} cos1={row['cos1']:.5f} "
        f"sin2={row['sin2']:.5f} cos2={row['cos2']:.5f}"
      )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
