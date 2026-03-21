#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, "/home/gericho/sunnypilot")
from opendbc.car.logreader import LogReader


def route_to_rlog(route: str) -> str:
  p = Path(route)
  if p.is_file():
    return str(p)
  if p.name == "rlog.zst":
    return str(p)
  return str(p / "rlog.zst")


def main() -> int:
  ap = argparse.ArgumentParser(description="Probe BMW i3 candidate signals from a route rlog")
  ap.add_argument("route", help="route dir or rlog.zst path")
  args = ap.parse_args()

  counters: dict[str, Counter] = {
    "fr_0_131_gate": Counter(),
    "fr_0_135_state": Counter(),
    "fr_1_97_ab": Counter(),
    "can_2_415_word": Counter(),
    "can_2_239_word": Counter(),
    "can_2_796_b1": Counter(),
    "can_2_217_acc12": Counter(),
  }

  for evt in LogReader(route_to_rlog(args.route), only_union_types=True):
    if evt.which() != "can":
      continue
    for m in evt.can:
      dat = bytes(m.dat)
      if (m.src, m.address) == (0, 131) and len(dat) >= 7:
        counters["fr_0_131_gate"][dat[5] | (dat[6] << 8)] += 1
      elif (m.src, m.address) == (0, 135) and len(dat) >= 7:
        counters["fr_0_135_state"][dat[5] | (dat[6] << 8)] += 1
      elif (m.src, m.address) == (1, 97) and len(dat) >= 5:
        a = dat[1] | (dat[2] << 8)
        b = dat[3] | (dat[4] << 8)
        counters["fr_1_97_ab"][(a, b)] += 1
      elif (m.src, m.address) == (2, 415) and len(dat) >= 4:
        counters["can_2_415_word"][dat[2] | (dat[3] << 8)] += 1
      elif (m.src, m.address) == (2, 239) and len(dat) >= 2:
        counters["can_2_239_word"][dat[0] | (dat[1] << 8)] += 1
      elif (m.src, m.address) == (2, 796) and len(dat) >= 2:
        counters["can_2_796_b1"][dat[1]] += 1
      elif (m.src, m.address) == (2, 217) and len(dat) >= 4:
        raw = ((dat[2] | (dat[3] << 8)) >> 0) & 0xFFF
        counters["can_2_217_acc12"][raw] += 1

  for name, counter in counters.items():
    print(f"\n## {name}")
    print(counter.most_common(16))

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
