#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean

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


def mode(gate: int | None, state: int | None) -> str:
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


def analyze_family(paths: list[str]) -> dict:
  gate = None
  state = None
  out = {
    "59": defaultdict(Counter),
    "54": defaultdict(Counter),
    "59_zero": Counter(),
    "54_zero": Counter(),
    "59_nonzero": Counter(),
    "54_nonzero": Counter(),
    "59_mean": defaultdict(list),
    "54_mean": defaultdict(list),
  }
  for path in paths:
    if not Path(path).exists():
      continue
    for evt in LogReader(path):
      if evt.which() != "can":
        continue
      for m in evt.can:
        dat = bytes(m.dat)
        if (m.src, m.address) == (0, 131) and len(dat) >= 7:
          gate = u16(dat, 5)
        elif (m.src, m.address) == (0, 135) and len(dat) >= 7:
          state = u16(dat, 5)
        elif (m.src, m.address) == (1, 59) and len(dat) >= 7:
          md = mode(gate, state)
          tup = (u16(dat, 3), u16(dat, 5), dat[0])
          out["59"][md][tup] += 1
          if tup[0] == 0 and tup[1] == 0:
            out["59_zero"][md] += 1
          else:
            out["59_nonzero"][md] += 1
            out["59_mean"][md].append(u16(dat, 3))
        elif (m.src, m.address) == (1, 54) and len(dat) >= 7:
          md = mode(gate, state)
          tup = (u16(dat, 3), u16(dat, 5), dat[0])
          out["54"][md][tup] += 1
          if tup[0] == 0 and tup[1] == 0:
            out["54_zero"][md] += 1
          else:
            out["54_nonzero"][md] += 1
            out["54_mean"][md].append(u16(dat, 3))
  return out


def main() -> int:
  for name, paths in ROUTE_FAMILIES.items():
    stats = analyze_family(paths)
    print(f"\n## {name}")
    for md in ("ACC_ARMED", "MANAGED"):
      nz59 = stats["59_nonzero"][md]
      z59 = stats["59_zero"][md]
      nz54 = stats["54_nonzero"][md]
      z54 = stats["54_zero"][md]
      print(
        f"{md}: 59 nz={nz59} z={z59} mean_wB={fmean(stats['59_mean'][md]):.2f}" if stats["59_mean"][md] else f"{md}: 59 nz={nz59} z={z59} mean_wB=n/a"
      )
      print(
        f"{md}: 54 nz={nz54} z={z54} mean_wB={fmean(stats['54_mean'][md]):.2f}" if stats["54_mean"][md] else f"{md}: 54 nz={nz54} z={z54} mean_wB=n/a"
      )
      print(f"{md}: 59 top {stats['59'][md].most_common(6)}")
      print(f"{md}: 54 top {stats['54'][md].most_common(6)}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
