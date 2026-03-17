#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional

sys.path.insert(0, "/home/gericho/sunnypilot")
from opendbc.car.logreader import LogReader


def resolve_latest_route() -> Optional[Path]:
  root = Path("/home/gericho/.comma/media/0/realdata")
  candidates = sorted(root.glob("*--0"), key=lambda p: p.stat().st_mtime, reverse=True)
  return candidates[0] if candidates else None


def route_to_rlog(route: str) -> str:
  p = Path(route)
  if p.is_file():
    return str(p)
  if p.name == "rlog.zst":
    return str(p)
  return str(p / "rlog.zst")


def u16_le(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


def main() -> int:
  ap = argparse.ArgumentParser(description="Second-by-second BMW i3 replay summary for shadow/debug correlation")
  ap.add_argument("route", nargs="?", help="route dir or rlog.zst path; omit to use latest route")
  args = ap.parse_args()

  route = args.route
  if route is None:
    latest = resolve_latest_route()
    if latest is None:
      raise FileNotFoundError("no routes found in /home/gericho/.comma/media/0/realdata")
    route = str(latest)

  print(f"# route {route}")

  state = {
    "gate131": None,
    "state135": None,
    "lat72_phase": None,
    "lat72_cnt": None,
    "lat72_flag": None,
    "lat96_b0": None,
    "lat96_b1": None,
    "lat96_b2": None,
    "lat96_b3": None,
    "lat96_b4": None,
    "long59_wb": None,
    "long59_wc": None,
    "long59_b3": None,
    "long59_b5": None,
    "long54_wb": None,
    "long54_wc": None,
    "long54_b4": None,
    "long54_b6": None,
  }

  first_ts = None
  last_sec = -1

  print("# sec gate131 state135 lat72(phase,cnt,flag) lat96(b0,b1,b2,b3,b4) long59(wb,wc,b3,b5) long54(wb,wc,b4,b6)")

  for evt in LogReader(route_to_rlog(route), only_union_types=True):
    if evt.which() != "can":
      continue

    evt_ts = evt.logMonoTime / 1e9
    if first_ts is None:
      first_ts = evt_ts
    sec = int(evt_ts - first_ts)

    for m in evt.can:
      dat = bytes(m.dat)
      if (m.src, m.address) == (0, 131) and len(dat) >= 7:
        state["gate131"] = u16_le(dat, 5)
      elif (m.src, m.address) == (0, 135) and len(dat) >= 7:
        state["state135"] = u16_le(dat, 5)
      elif (m.src, m.address) == (0, 72) and len(dat) >= 9:
        state["lat72_phase"] = dat[0]
        state["lat72_cnt"] = dat[2] & 0x0F
        state["lat72_flag"] = dat[8]
      elif (m.src, m.address) == (0, 96) and len(dat) >= 9:
        state["lat96_b0"] = dat[0]
        state["lat96_b1"] = dat[1]
        state["lat96_b2"] = dat[2]
        state["lat96_b3"] = dat[3]
        state["lat96_b4"] = dat[4]
      elif (m.src, m.address) == (1, 59) and len(dat) >= 6:
        state["long59_wb"] = u16_le(dat, 3)
        state["long59_wc"] = u16_le(dat, 5)
        state["long59_b3"] = dat[3]
        state["long59_b5"] = dat[5]
      elif (m.src, m.address) == (1, 54) and len(dat) >= 7:
        state["long54_wb"] = u16_le(dat, 3)
        state["long54_wc"] = u16_le(dat, 5)
        state["long54_b4"] = dat[4]
        state["long54_b6"] = dat[6]

    if sec != last_sec and sec >= 0:
      def f(key):
        v = state[key]
        return "-" if v is None else str(v)

      print(
        f"{sec:4d} "
        f"{f('gate131'):>6} {f('state135'):>6} "
        f"({f('lat72_phase')},{f('lat72_cnt')},{f('lat72_flag')}) "
        f"({f('lat96_b0')},{f('lat96_b1')},{f('lat96_b2')},{f('lat96_b3')},{f('lat96_b4')}) "
        f"({f('long59_wb')},{f('long59_wc')},{f('long59_b3')},{f('long59_b5')}) "
        f"({f('long54_wb')},{f('long54_wc')},{f('long54_b4')},{f('long54_b6')})"
      )
      last_sec = sec

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
