#!/usr/bin/env python3
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
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

CANDIDATES = {
  (1, 97): ("u16", 1),
  (2, 217): ("u12_hi", 2),
  (2, 239): ("u16", 0),
  (2, 415): ("u16", 2),
  (2, 796): ("u8", 1),
}


def u16(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


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


def extract_value(dat: bytes, kind: str, off: int) -> int:
  if kind == "u16":
    return u16(dat, off)
  if kind == "u8":
    return dat[off]
  if kind == "u12_hi":
    return (u16(dat, off) >> 0) & 0xFFF
  raise ValueError(kind)


def collect_family(paths: list[str]) -> tuple[list[dict], dict[tuple[int, int], list[dict]]]:
  plan_rows: list[dict] = []
  cand_rows: dict[tuple[int, int], list[dict]] = defaultdict(list)
  for path in paths:
    if not Path(path).exists():
      continue
    for evt in LogReader(path):
      t = evt.logMonoTime / 1e9
      which = evt.which()
      if which == "longitudinalPlan":
        lp = evt.longitudinalPlan
        plan_rows.append({"t": t, "aTarget": float(lp.aTarget)})
        continue
      if which != "can":
        continue
      for m in evt.can:
        key = (m.src, m.address)
        if key not in CANDIDATES:
          continue
        dat = bytes(m.dat)
        kind, off = CANDIDATES[key]
        if (kind == "u16" and len(dat) < off + 2) or (kind == "u8" and len(dat) < off + 1) or (kind == "u12_hi" and len(dat) < off + 2):
          continue
        cand_rows[key].append({"t": t, "value": float(extract_value(dat, kind, off))})
  return plan_rows, cand_rows


def evaluate(series: list[dict], plans: list[dict], tol_s: float) -> tuple[int, Optional[float], Optional[float]]:
  if not series or not plans:
    return 0, None, None
  times = [r["t"] for r in plans]
  xs: list[float] = []
  ys: list[float] = []
  for s in series:
    idx = nearest_index(times, s["t"], tol_s)
    if idx is None:
      continue
    xs.append(s["value"])
    ys.append(plans[idx]["aTarget"])
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
  tol_s = 0.08
  all_plans: list[dict] = []
  all_cands: dict[tuple[int, int], list[dict]] = defaultdict(list)
  for name, paths in ROUTE_FAMILIES.items():
    plans, cands = collect_family(paths)
    all_plans.extend(plans)
    for key, rows in cands.items():
      all_cands[key].extend(rows)
    print(f"\n## {name}")
    for key in sorted(CANDIDATES):
      print(f"{key}: {evaluate(cands.get(key, []), plans, tol_s)}")

  print("\n## ALL")
  for key in sorted(CANDIDATES):
    print(f"{key}: {evaluate(all_cands.get(key, []), all_plans, tol_s)}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
