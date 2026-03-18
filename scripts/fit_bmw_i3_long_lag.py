#!/usr/bin/env python3
from __future__ import annotations

import argparse
from bisect import bisect_left
from pathlib import Path
from statistics import fmean
from typing import Optional

from tools.lib.logreader import LogReader


ROUTE_FAMILIES = {
  "147_acc": ["/home/gericho/.comma/media/0/realdata/00000147--1294d32c66--0/rlog.zst"],
  "148_acc": ["/home/gericho/.comma/media/0/realdata/00000148--ddcfbc9103--0/rlog.zst"],
  "176_tja": ["/home/gericho/.comma/media/0/realdata/00000176--3a6e928ca3--0/rlog.zst"],
  "177_tja": [
    "/home/gericho/.comma/media/0/realdata/00000177--e20f5033b4--0/rlog.zst",
    "/home/gericho/.comma/media/0/realdata/00000177--e20f5033b4--1/rlog.zst",
    "/home/gericho/.comma/media/0/realdata/00000177--e20f5033b4--2/rlog.zst",
  ],
  "170_misc": [
    "/home/gericho/.comma/media/0/realdata/00000170--2122025789--0/rlog.zst",
    "/home/gericho/.comma/media/0/realdata/00000170--2122025789--1/rlog.zst",
    "/home/gericho/.comma/media/0/realdata/00000170--2122025789--2/rlog.zst",
    "/home/gericho/.comma/media/0/realdata/00000170--2122025789--3/rlog.zst",
  ],
}

LONG_59_CENTER_WB = 32777
LONG_59_CENTER_WC = 32767
LONG_54_CENTER_WB = 65025
LONG_54_CENTER_WC = 7


def u16(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


def delta_u16(val: int, center: int) -> int:
  return ((val - center + 32768) % 65536) - 32768


def mode(gate: Optional[int], state: Optional[int]) -> str:
  if gate is None or state is None:
    return "UNKNOWN"
  if gate == 643 and state == 35041:
    return "OFF"
  if gate == 3584 and state == 16610:
    return "ACC_ARMED"
  if gate in (640, 656) and state == 24802:
    return "MANAGED"
  if state == 26850 or gate in (640, 656):
    return "TRANSITION"
  return "UNKNOWN"


def pearson(xs: list[float], ys: list[float]) -> Optional[float]:
  if len(xs) < 2 or len(xs) != len(ys):
    return None
  mx = fmean(xs)
  my = fmean(ys)
  num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
  denx = sum((x - mx) ** 2 for x in xs)
  deny = sum((y - my) ** 2 for y in ys)
  if denx <= 0 or deny <= 0:
    return None
  return num / ((denx * deny) ** 0.5)


def nearest_index(times: list[float], target: float, tol: float) -> Optional[int]:
  i = bisect_left(times, target)
  candidates = []
  if i < len(times):
    candidates.append(i)
  if i > 0:
    candidates.append(i - 1)
  if not candidates:
    return None
  best = min(candidates, key=lambda idx: abs(times[idx] - target))
  if abs(times[best] - target) > tol:
    return None
  return best


def collect_family(paths: list[str], alpha: float) -> tuple[list[dict], list[dict]]:
  cs_rows: list[dict] = []
  frame_rows: list[dict] = []
  gate = None
  state = None
  prev_t = None
  prev_v = None
  a_filt = None

  for path in paths:
    if not Path(path).exists():
      continue
    for evt in LogReader(path):
      t = evt.logMonoTime / 1e9
      which = evt.which()
      if which == "carState":
        cs = evt.carState
        v = float(cs.vEgo)
        raw_a = float(cs.aEgo) if prev_t is None or prev_v is None else (v - prev_v) / max(t - prev_t, 1e-3)
        a_filt = raw_a if a_filt is None else (alpha * raw_a + (1.0 - alpha) * a_filt)
        prev_t = t
        prev_v = v
        cs_rows.append({
          "t": t,
          "vEgo": v,
          "aProxy": a_filt,
          "gasPressed": bool(cs.gasPressed),
          "standstill": bool(cs.standstill),
        })
        continue

      if which != "can":
        continue

      for m in evt.can:
        dat = bytes(m.dat)
        if (m.src, m.address) == (0, 131) and len(dat) >= 7:
          gate = u16(dat, 5)
        elif (m.src, m.address) == (0, 135) and len(dat) >= 7:
          state = u16(dat, 5)
        elif (m.src, m.address) == (1, 59) and len(dat) >= 7:
          md = mode(gate, state)
          if md not in ("ACC_ARMED", "MANAGED"):
            continue
          w_b = u16(dat, 3)
          w_c = u16(dat, 5)
          if w_b == 0 and w_c == 0:
            continue
          delta = delta_u16(w_b, LONG_59_CENTER_WB) + 0.5 * delta_u16(w_c, LONG_59_CENTER_WC)
          frame_rows.append({"t": t, "mode": md, "branch": 59, "phase": dat[0], "wB": w_b, "wC": w_c, "delta": float(delta)})
        elif (m.src, m.address) == (1, 54) and len(dat) >= 7:
          md = mode(gate, state)
          if md not in ("ACC_ARMED", "MANAGED"):
            continue
          w_b = u16(dat, 3)
          w_c = u16(dat, 5)
          if w_b == 0 and w_c == 0:
            continue
          delta = delta_u16(w_b, LONG_54_CENTER_WB) + 0.5 * delta_u16(w_c, LONG_54_CENTER_WC)
          frame_rows.append({"t": t, "mode": md, "branch": 54, "phase": dat[0], "wB": w_b, "wC": w_c, "delta": float(delta)})
  return cs_rows, frame_rows


def evaluate_branch(frames: list[dict], cs_rows: list[dict], lag_s: float, sign: float, tol: float, managed_only: bool) -> tuple[int, Optional[float], Optional[float]]:
  if managed_only:
    frames = [f for f in frames if f["mode"] == "MANAGED"]
  if not frames or not cs_rows:
    return 0, None, None
  times = [r["t"] for r in cs_rows]
  xs: list[float] = []
  ys: list[float] = []
  for f in frames:
    idx = nearest_index(times, f["t"] + lag_s, tol)
    if idx is None:
      continue
    cs = cs_rows[idx]
    if cs["gasPressed"] or cs["standstill"] or cs["vEgo"] < 1.0:
      continue
    xs.append(f["delta"])
    ys.append(sign * float(cs["aProxy"]))
  corr = pearson(xs, ys)
  slope = None
  if corr is not None and len(xs) >= 2:
    mx = fmean(xs)
    my = fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den > 0:
      slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
  return len(xs), corr, slope


def main() -> int:
  ap = argparse.ArgumentParser(description="Fit BMW i3 long branches against future acceleration with lag")
  ap.add_argument("--alpha", type=float, default=0.35, help="EMA alpha for dv/dt")
  ap.add_argument("--lag-max-ms", type=int, default=1500)
  ap.add_argument("--lag-step-ms", type=int, default=50)
  ap.add_argument("--tol-ms", type=int, default=80)
  args = ap.parse_args()

  family_data = {}
  all_cs: list[dict] = []
  all_frames: list[dict] = []
  for name, paths in ROUTE_FAMILIES.items():
    cs_rows, frame_rows = collect_family(paths, alpha=args.alpha)
    family_data[name] = (cs_rows, frame_rows)
    all_cs.extend(cs_rows)
    all_frames.extend(frame_rows)

  def scan(name: str, cs_rows: list[dict], frame_rows: list[dict]) -> None:
    print(f"\n## {name}")
    for branch, sign in ((59, 1.0), (54, -1.0)):
      branch_frames = [f for f in frame_rows if f["branch"] == branch]
      best_any = None
      best_managed = None
      for lag_ms in range(0, args.lag_max_ms + args.lag_step_ms, args.lag_step_ms):
        lag_s = lag_ms / 1000.0
        res_any = evaluate_branch(branch_frames, cs_rows, lag_s, sign, args.tol_ms / 1000.0, managed_only=False)
        res_man = evaluate_branch(branch_frames, cs_rows, lag_s, sign, args.tol_ms / 1000.0, managed_only=True)
        n_any, corr_any, slope_any = res_any
        n_man, corr_man, slope_man = res_man
        if corr_any is not None:
          cand = (abs(corr_any), lag_ms, n_any, corr_any, slope_any)
          if best_any is None or cand > best_any:
            best_any = cand
        if corr_man is not None:
          cand = (abs(corr_man), lag_ms, n_man, corr_man, slope_man)
          if best_managed is None or cand > best_managed:
            best_managed = cand
      print(f"branch {branch} best_any={best_any}")
      print(f"branch {branch} best_managed={best_managed}")

  for name, (cs_rows, frame_rows) in family_data.items():
    scan(name, cs_rows, frame_rows)
  scan("ALL", all_cs, all_frames)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
