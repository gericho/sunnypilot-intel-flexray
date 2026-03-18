#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from opendbc.car.logreader import LogReader


LONG_59_ACTIVE_PARITY = 0
LONG_54_ACTIVE_PARITY = 1
LONG_59_CENTER_WB = 32777
LONG_59_CENTER_WC = 32767
LONG_54_CENTER_WB = 65025
LONG_54_CENTER_WC = 7


def resolve_latest_route() -> Optional[Path]:
  root = Path("/home/gericho/.comma/media/0/realdata")
  candidates = sorted(root.glob("*--0"), key=lambda p: p.stat().st_mtime, reverse=True)
  return candidates[0] if candidates else None


def expand_route_segments(route: str) -> list[Path]:
  p = Path(route)
  if p.is_file():
    if p.name.endswith(".zst"):
      return [p]
    raise FileNotFoundError(f"unsupported file path: {p}")
  if p.name.endswith("--0"):
    stem = p.name[:-1]
    base = p.parent
  elif "--" in p.name and p.name.rsplit("--", 1)[-1].isdigit():
    stem = p.name.rsplit("--", 1)[0] + "--"
    base = p.parent
  else:
    stem = p.name
    base = p.parent
  segs = sorted(base.glob(f"{stem}[0-9]*"))
  out = []
  for seg in segs:
    for name in ("rlog.zst", "qlog.zst"):
      pth = seg / name
      if pth.exists():
        out.append(pth)
        break
  if not out:
    raise FileNotFoundError(f"no route segments found for {route}")
  return out


def u16_le(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


def mode_name(gate: int | None, state: int | None) -> str:
  if gate is None or state is None:
    return "UNKNOWN"
  if gate == 643 and state == 35041:
    return "OFF"
  if gate == 3584 and state == 16610:
    return "ACC_ARMED"
  if gate in (640, 656) and state == 24802:
    return "MANAGED"
  if state == 26850 or (gate in (640, 656) and state == 16610):
    return "TRANSITION"
  return "UNKNOWN"


def active_branch(d59: bytes | None, d54: bytes | None) -> tuple[str, int | None]:
  if d59 is not None and u16_le(d59, 3) != 0:
    return "59", d59[0]
  if d54 is not None and u16_le(d54, 3) != 0:
    return "54", d54[0]
  return "idle", None


def main() -> int:
  ap = argparse.ArgumentParser(description="Build conservative BMW i3 long replay hints from a route")
  ap.add_argument("route", nargs="?", help="route dir/segment; omit to use latest route")
  args = ap.parse_args()

  route = args.route
  if route is None:
    latest = resolve_latest_route()
    if latest is None:
      raise FileNotFoundError("no routes found")
    route = str(latest)

  gate = None
  state = None
  d59 = None
  d54 = None
  first_ts = None
  last_sec = -1
  sec_rows = []
  phase_counts = defaultdict(Counter)

  for rlog in expand_route_segments(route):
    for evt in LogReader(str(rlog), only_union_types=True):
      if evt.which() != "can":
        continue
      ts = evt.logMonoTime / 1e9
      if first_ts is None:
        first_ts = ts
      sec = int(ts - first_ts)
      for m in evt.can:
        dat = bytes(m.dat)
        if (m.src, m.address) == (0, 131) and len(dat) >= 7:
          gate = u16_le(dat, 5)
        elif (m.src, m.address) == (0, 135) and len(dat) >= 7:
          state = u16_le(dat, 5)
        elif (m.src, m.address) == (1, 59) and len(dat) >= 7:
          d59 = dat
        elif (m.src, m.address) == (1, 54) and len(dat) >= 7:
          d54 = dat
      if sec != last_sec and sec >= 0:
        mode = mode_name(gate, state)
        branch, phase = active_branch(d59, d54)
        sec_rows.append((sec, mode, branch, phase))
        if phase is not None:
          phase_counts[(mode, branch)][phase] += 1
        last_sec = sec

  print(f"# route {route}")
  print("# sec mode branch phase replay_hint")
  for sec, mode, branch, phase in sec_rows:
    if mode not in ("ACC_ARMED", "MANAGED", "TRANSITION"):
      continue
    if branch == "59":
      hint = f"59 parity={LONG_59_ACTIVE_PARITY} target=({LONG_59_CENTER_WB},{LONG_59_CENTER_WC})"
    elif branch == "54":
      hint = f"54 parity={LONG_54_ACTIVE_PARITY} target=({LONG_54_CENTER_WB},{LONG_54_CENTER_WC})"
    else:
      hint = "idle"
    print(f"{sec:4d} {mode:10s} {branch:4s} {str(phase):>4s} {hint}")

  print("\n# dominant phase families")
  for (mode, branch), counts in sorted(phase_counts.items()):
    common = ", ".join(f"{ph}:{n}" for ph, n in counts.most_common(8))
    print(f"{mode:10s} {branch:4s} {common}")

  print("\n# conservative replay template")
  print(f"positive/coast -> branch 59, parity {LONG_59_ACTIVE_PARITY}, center=({LONG_59_CENTER_WB},{LONG_59_CENTER_WC})")
  print(f"negative/brake -> branch 54, parity {LONG_54_ACTIVE_PARITY}, center=({LONG_54_CENTER_WB},{LONG_54_CENTER_WC})")
  print("always gate with 131/135 stock state")
  print("final payload scaling and checksum/counter are still open")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
