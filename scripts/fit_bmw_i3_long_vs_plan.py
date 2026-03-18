#!/usr/bin/env python3
from __future__ import annotations

import argparse
from bisect import bisect_left
from pathlib import Path
from statistics import fmean, median
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


def collect_family(paths: list[str]) -> tuple[list[dict], list[dict]]:
  plan_rows: list[dict] = []
  frame_rows: list[dict] = []
  gate = None
  state = None
  for path in paths:
    if not Path(path).exists():
      continue
    for evt in LogReader(path):
      t = evt.logMonoTime / 1e9
      which = evt.which()
      if which == "longitudinalPlan":
        lp = evt.longitudinalPlan
        accels = list(lp.accels)
        plan_rows.append({
          "t": t,
          "aTarget": float(lp.aTarget),
          "a0": float(accels[0]) if accels else float(lp.aTarget),
          "hasLead": bool(lp.hasLead),
          "source": str(lp.longitudinalPlanSource),
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
  return plan_rows, frame_rows


def evaluate_branch(frames: list[dict], plan_rows: list[dict], tol_s: float, managed_only: bool) -> tuple[int, Optional[float], Optional[float]]:
  if managed_only:
    frames = [f for f in frames if f["mode"] == "MANAGED"]
  if not frames or not plan_rows:
    return 0, None, None
  times = [r["t"] for r in plan_rows]
  xs: list[float] = []
  ys: list[float] = []
  for f in frames:
    idx = nearest_index(times, f["t"], tol_s)
    if idx is None:
      continue
    pr = plan_rows[idx]
    xs.append(f["delta"])
    ys.append(pr["aTarget"])
  corr = pearson(xs, ys)
  slope = None
  if corr is not None and len(xs) >= 2:
    mx = fmean(xs)
    my = fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den > 0:
      slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
  return len(xs), corr, slope


def summarize_samples(frames: list[dict], plan_rows: list[dict], tol_s: float) -> None:
  times = [r["t"] for r in plan_rows]
  print("\n# bucket medians vs aTarget")
  buckets = {
    "POS": lambda a: a > 0.15,
    "COAST": lambda a: -0.15 <= a <= 0.15,
    "NEG": lambda a: a < -0.15,
  }
  acc = {59: {k: [] for k in buckets}, 54: {k: [] for k in buckets}}
  for f in frames:
    if f["mode"] != "MANAGED":
      continue
    idx = nearest_index(times, f["t"], tol_s)
    if idx is None:
      continue
    a = plan_rows[idx]["aTarget"]
    for name, pred in buckets.items():
      if pred(a):
        acc[f["branch"]][name].append((f["wB"], f["wC"], f["delta"], a))
        break
  for branch in (59, 54):
    for bucket in ("POS", "COAST", "NEG"):
      arr = acc[branch][bucket]
      if not arr:
        continue
      print(
        f"{branch} {bucket}: n={len(arr)} "
        f"a_med={median([x[3] for x in arr]):.4f} "
        f"wB_med={median([x[0] for x in arr])} "
        f"wC_med={median([x[1] for x in arr])} "
        f"delta_med={median([x[2] for x in arr]):.1f}"
      )


def main() -> int:
  ap = argparse.ArgumentParser(description="Fit BMW i3 long branches against longitudinalPlan.aTarget")
  ap.add_argument("--tol-ms", type=int, default=80)
  args = ap.parse_args()

  all_plans: list[dict] = []
  all_frames: list[dict] = []
  for name, paths in ROUTE_FAMILIES.items():
    plan_rows, frame_rows = collect_family(paths)
    all_plans.extend(plan_rows)
    all_frames.extend(frame_rows)
    print(f"\n## {name}")
    for branch in (59, 54):
      bf = [f for f in frame_rows if f["branch"] == branch]
      print(f"branch {branch} any={evaluate_branch(bf, plan_rows, args.tol_ms / 1000.0, managed_only=False)}")
      print(f"branch {branch} managed={evaluate_branch(bf, plan_rows, args.tol_ms / 1000.0, managed_only=True)}")

  print("\n## ALL")
  for branch in (59, 54):
    bf = [f for f in all_frames if f["branch"] == branch]
    print(f"branch {branch} any={evaluate_branch(bf, all_plans, args.tol_ms / 1000.0, managed_only=False)}")
    print(f"branch {branch} managed={evaluate_branch(bf, all_plans, args.tol_ms / 1000.0, managed_only=True)}")
  summarize_samples(all_frames, all_plans, args.tol_ms / 1000.0)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
