#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from opendbc.car.logreader import LogReader


ROOT = Path("/home/gericho/.comma/media/0/realdata")


def route_groups_for_day(day: str) -> dict[str, list[Path]]:
  groups: dict[str, list[Path]] = defaultdict(list)
  for seg in sorted(ROOT.glob("*--*")):
    if not seg.is_dir():
      continue
    st = seg.stat()
    from datetime import datetime
    ds = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
    if ds != day:
      continue
    base = seg.name.rsplit("--", 1)[0]
    groups[base].append(seg)
  return dict(sorted(groups.items()))


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
  if state == 26850:
    return "TRANSITION"
  return "UNKNOWN"


def iter_can(route_segments: Iterable[Path]):
  for seg in route_segments:
    rlog = seg / "qlog.zst"
    if not rlog.exists():
      rlog = seg / "rlog.zst"
    if not rlog.exists():
      continue
    for evt in LogReader(str(rlog), only_union_types=True):
      if evt.which() == "can":
        yield evt


def summarize_group(route_id: str, segs: list[Path]) -> dict[str, object]:
  first_ts = None
  last_sec = -1
  gate = None
  state = None
  mode_counts = Counter()
  transitions: list[tuple[int, str]] = []
  tja_button_count = 0
  acc_button_count = 0
  set_count = 0
  res_count = 0

  for evt in iter_can(segs):
    evt_ts = evt.logMonoTime / 1e9
    if first_ts is None:
      first_ts = evt_ts
    sec = int(evt_ts - first_ts)
    for m in evt.can:
      dat = bytes(m.dat)
      if (m.src, m.address) == (0, 131) and len(dat) >= 7:
        gate = u16_le(dat, 5)
      elif (m.src, m.address) == (0, 135) and len(dat) >= 7:
        state = u16_le(dat, 5)
      elif (m.src, m.address) == (0, 97) and len(dat) >= 7:
        val = u16_le(dat, 5)
        if val == 30716:
          acc_button_count += 1
        elif val == 18684:
          tja_button_count += 1
      elif (m.src, m.address) == (2, 415) and len(dat) >= 2:
        v = u16_le(dat, 0)
        if v == 0x8015:
          set_count += 1
        elif v == 0x8016:
          res_count += 1
    if sec != last_sec and sec >= 0:
      mode = mode_name(gate, state)
      mode_counts[mode] += 1
      if not transitions or transitions[-1][1] != mode:
        transitions.append((sec, mode))
      last_sec = sec

  return {
    "route_id": route_id,
    "segments": len(segs),
    "seconds": max(last_sec + 1, 0),
    "mode_counts": mode_counts,
    "transitions": transitions,
    "acc_button_count": acc_button_count,
    "tja_button_count": tja_button_count,
    "set_count": set_count,
    "res_count": res_count,
  }


def main() -> int:
  day = "2026-03-17"
  groups = route_groups_for_day(day)
  print(f"# BMW i3 routes for {day}")
  print("# route_id segs secs off armed managed transition acc_btn tja_btn set res")
  for route_id, segs in groups.items():
    s = summarize_group(route_id, segs)
    counts = s["mode_counts"]
    active = counts.get("ACC_ARMED", 0) or counts.get("MANAGED", 0) or s["tja_button_count"] or s["acc_button_count"] or s["set_count"] or s["res_count"]
    if active:
      print(
        f"{route_id} {s['segments']:>3} {s['seconds']:>4} "
        f"{counts.get('OFF', 0):>4} {counts.get('ACC_ARMED', 0):>5} {counts.get('MANAGED', 0):>7} {counts.get('TRANSITION', 0):>10} "
        f"{s['acc_button_count']:>7} {s['tja_button_count']:>7} {s['set_count']:>3} {s['res_count']:>3}"
      )
      trans = ", ".join(f"{sec}:{mode}" for sec, mode in s["transitions"][:12])
      print(f"  transitions: {trans}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
