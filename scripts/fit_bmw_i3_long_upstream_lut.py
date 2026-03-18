#!/usr/bin/env python3
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
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


def u16(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


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


def bucket(a: float) -> str:
  if a > 0.15:
    return "POS"
  if a < -0.15:
    return "NEG"
  return "COAST"


def collect() -> list[dict]:
  rows: list[dict] = []
  for paths in ROUTE_FAMILIES.values():
    gate = None
    state = None
    plan_rows: list[dict] = []
    cand217: list[dict] = []
    cand796: list[dict] = []
    long59: list[dict] = []
    long54: list[dict] = []
    for path in paths:
      if not Path(path).exists():
        continue
      for evt in LogReader(path):
        t = evt.logMonoTime / 1e9
        w = evt.which()
        if w == "longitudinalPlan":
          lp = evt.longitudinalPlan
          plan_rows.append({"t": t, "aTarget": float(lp.aTarget)})
        elif w == "can":
          for m in evt.can:
            dat = bytes(m.dat)
            if (m.src, m.address) == (0, 131) and len(dat) >= 7:
              gate = u16(dat, 5)
            elif (m.src, m.address) == (0, 135) and len(dat) >= 7:
              state = u16(dat, 5)
            elif mode(gate, state) in ("ACC_ARMED", "MANAGED"):
              if (m.src, m.address) == (2, 217) and len(dat) >= 4:
                cand217.append({"t": t, "mode": mode(gate, state), "raw16": u16(dat, 0), "compat12": u16(dat, 2) & 0xFFF})
              elif (m.src, m.address) == (2, 796) and len(dat) >= 2:
                cand796.append({"t": t, "mode": mode(gate, state), "raw16": u16(dat, 0), "b1": dat[1]})
              elif (m.src, m.address) == (1, 59) and len(dat) >= 7:
                long59.append({"t": t, "mode": mode(gate, state), "wB": u16(dat, 3), "wC": u16(dat, 5)})
              elif (m.src, m.address) == (1, 54) and len(dat) >= 7:
                long54.append({"t": t, "mode": mode(gate, state), "wB": u16(dat, 3), "wC": u16(dat, 5)})
    if not plan_rows:
      continue
    times = [r["t"] for r in plan_rows]
    for s in cand217:
      i = nearest_index(times, s["t"], 0.08)
      if i is None:
        continue
      s["aTarget"] = plan_rows[i]["aTarget"]
      s["bucket"] = bucket(s["aTarget"])
    for s in cand796:
      i = nearest_index(times, s["t"], 0.08)
      if i is None:
        continue
      s["aTarget"] = plan_rows[i]["aTarget"]
      s["bucket"] = bucket(s["aTarget"])
    for s in long59:
      i = nearest_index(times, s["t"], 0.08)
      if i is None:
        continue
      s["aTarget"] = plan_rows[i]["aTarget"]
      s["bucket"] = bucket(s["aTarget"])
    for s in long54:
      i = nearest_index(times, s["t"], 0.08)
      if i is None:
        continue
      s["aTarget"] = plan_rows[i]["aTarget"]
      s["bucket"] = bucket(s["aTarget"])
    rows.append({"217": cand217, "796": cand796, "59": long59, "54": long54})
  return rows


def print_bucket_summary(name: str, rows: list[dict], keys: list[str]) -> None:
  print(f"\n## {name}")
  for bucket_name in ("POS", "COAST", "NEG"):
    arr = [r for r in rows if r.get("bucket") == bucket_name and r.get("mode") == "MANAGED"]
    if not arr:
      continue
    fields = " ".join(f"{k}_med={median([r[k] for r in arr])}" for k in keys)
    print(f"{bucket_name}: n={len(arr)} a_med={median([r['aTarget'] for r in arr]):.4f} {fields}")


def main() -> int:
  data = collect()
  all217 = [r for fam in data for r in fam["217"]]
  all796 = [r for fam in data for r in fam["796"]]
  all59 = [r for fam in data for r in fam["59"]]
  all54 = [r for fam in data for r in fam["54"]]

  print_bucket_summary("217", all217, ["raw16", "compat12"])
  print_bucket_summary("796", all796, ["raw16", "b1"])
  print_bucket_summary("59", all59, ["wB", "wC"])
  print_bucket_summary("54", all54, ["wB", "wC"])

  print("\n# pragmatic upstream LUT")
  pos = [r for r in all217 if r.get("bucket") == "POS" and r.get("mode") == "MANAGED"]
  coast = [r for r in all217 if r.get("bucket") == "COAST" and r.get("mode") == "MANAGED"]
  neg = [r for r in all796 if r.get("bucket") == "NEG" and r.get("mode") == "MANAGED"]
  if pos:
    print(f"POS -> 217.raw16≈{median([r['raw16'] for r in pos])} compat12≈{median([r['compat12'] for r in pos])}")
  if coast:
    print(f"COAST -> 217.raw16≈{median([r['raw16'] for r in coast])} compat12≈{median([r['compat12'] for r in coast])}")
  if neg:
    print(f"NEG -> 796.raw16≈{median([r['raw16'] for r in neg])} b1≈{median([r['b1'] for r in neg])}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
