#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

import usb1

from tools.bmw_i3_direct_lat_sweep import open_picoflex_device, unpack_flexray_records


WATCH_IDS = {60, 72, 96, 106, 131, 135, 264, 269}


@dataclass
class FlexState:
  overflow: bytes = b""
  last: dict[int, bytes] | None = None
  last_ts: dict[int, float] | None = None

  def __post_init__(self) -> None:
    if self.last is None:
      self.last = {}
    if self.last_ts is None:
      self.last_ts = {}


def classify_context(frame131: bytes | None, frame135: bytes | None, frame96: bytes | None,
                     frame267: bytes | None, frame269: bytes | None) -> str:
  if frame131 is None and frame135 is None and frame96 is None and frame267 is None and frame269 is None:
    return "no-data"

  if (frame131 in (None, b"\x00" * len(frame131 or b""))) and (frame135 in (None, b"\x00" * len(frame135 or b""))):
    return "idle"

  p131 = frame131.hex() if frame131 else ""
  p135 = frame135.hex() if frame135 else ""

  manual_135 = "22e0e188" in p135
  acc_135 = "2228e260" in p135 and p135.endswith("a205")
  # Live ACC/TJA-family payloads do not keep a single stable tail across sessions,
  # so classify by the central family bytes instead of exact route tails.
  acc_family_135 = (
    "20e0e240" in p135 or
    "28e268" in p135 or
    "29e268" in p135 or
    ("2228e260" in p135 and not p135.endswith("a205"))
  )

  manual_131 = p131.endswith("bb8302ffff") or p131.endswith("ba8302ffff") or p131.endswith("b98302ffff")
  tja_131 = p131.endswith("00000effff") or p131.endswith("7f8002ffff") or p131.endswith("7d8002ffff") or p131.endswith("7c8002ffff")
  authority_135 = (
    "20e0e2403206" in p135 or
    "2228e2604206" in p135
  )
  fr_context = frame267 is not None or frame269 is not None or frame96 is not None

  if manual_131 or manual_135:
    return "manual"

  if authority_135 and tja_131 and fr_context:
    return "authority_like"

  if tja_131 and (acc_135 or acc_family_135):
    return "acc_family"
  if tja_131 or acc_135 or acc_family_135:
    return "acc_family"
  if manual_131 or manual_135:
    return "manual"
  if frame96 is not None:
    return "acc_family"
  return "mixed"


def poll_live_flex(dev, state: FlexState, timeout_ms: int) -> tuple[FlexState, int]:
  try:
    raw = bytes(dev.handle.bulkRead(0x81, 16384, timeout=timeout_ms))
  except usb1.USBErrorTimeout:
    return state, 0

  records, overflow = unpack_flexray_records(state.overflow + raw)
  last = dict(state.last)
  last_ts = dict(state.last_ts)
  now = time.monotonic()
  reads = 0
  for frame_id, source, _cycle, payload in records:
    if source == 0 and frame_id in WATCH_IDS:
      last[frame_id] = payload
      last_ts[frame_id] = now
      reads += 1
  return FlexState(overflow=overflow, last=last, last_ts=last_ts), reads


def main() -> int:
  ap = argparse.ArgumentParser(description="Live monitor for BMW i3 FlexRay 131/135/96 context")
  ap.add_argument("--hz", type=float, default=5.0, help="screen refresh rate")
  ap.add_argument("--duration", type=float, default=0.0, help="optional max run time in seconds; 0 means infinite")
  ap.add_argument("--serial", default="", help="optional picoflex USB serial")
  args = ap.parse_args()

  period = 1.0 / max(args.hz, 0.2)
  stale_s = max(0.6, period * 2.5)
  dev = open_picoflex_device(args.serial)
  try:
    state = FlexState()
    start = time.monotonic()
    last_print = 0.0
    print(f"# monitor serial={dev.serial} hz={args.hz:.1f}")
    print("# classify: idle | manual | acc_family | authority_like | mixed")
    while True:
      state, reads = poll_live_flex(dev, state, timeout_ms=max(1, int(period * 1000)))
      now = time.monotonic()
      if now - last_print >= period:
        def fresh(fid: int):
          ts = state.last_ts.get(fid)
          if ts is None or (now - ts) > stale_s:
            return None
          return state.last.get(fid)

        f96 = fresh(96)
        f131 = fresh(131)
        f135 = fresh(135)
        f267 = fresh(267)
        f269 = fresh(269)
        phase = f96[0] if f96 else None
        ctx = classify_context(f131, f135, f96, f267, f269)
        print(
          f"t={now - start:7.2f}s  ctx={ctx:14s}  phase96={str(phase):>4s}  fr_reads={reads:2d}  "
          f"131={(f131.hex() if f131 else 'None')}  135={(f135.hex() if f135 else 'None')}  "
          f"96={(f96.hex() if f96 else 'None')}  267={(f267.hex() if f267 else 'None')}  "
          f"269={(f269.hex() if f269 else 'None')}"
        )
        last_print = now
      if args.duration > 0.0 and now - start >= args.duration:
        break
  finally:
    dev.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
