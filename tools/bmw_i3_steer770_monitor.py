#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

from tools.bmw_i3_direct_lat_sweep import open_picoflex_device
from tools.bmw_i3_rlog_raw_inject import LiveCanState, configure_can_bitrate, read_can_health, unpack_can_buffer


def scale_770_live(raw: int) -> float:
  return (raw - 32748) * 0.03540


def poll_live_steer770_raw(dev, state: LiveCanState, timeout_ms: int) -> tuple[LiveCanState, int, int | None]:
  import usb1

  try:
    raw = bytes(dev.handle.bulkRead(0x82, 16384, timeout=timeout_ms))
  except usb1.USBErrorTimeout:
    return state, 0, None

  steer770 = state.steer770_deg
  steer770_raw = None
  records, overflow = unpack_can_buffer(state.overflow + raw)
  for address, payload, bus in records:
    if bus == 2 and address == 770 and len(payload) >= 4:
      steer770_raw = payload[2] | (payload[3] << 8)
      steer770 = scale_770_live(steer770_raw)
  return LiveCanState(steer770_deg=steer770, overflow=overflow), len(records), steer770_raw


def main() -> int:
  ap = argparse.ArgumentParser(description="Live monitor for BMW i3 steering angle from PT-CAN 770")
  ap.add_argument("--bus", type=int, default=2, help="CAN bus index on pico-flexray")
  ap.add_argument("--speed-kbps", type=int, default=500, help="CAN bitrate in kbps")
  ap.add_argument("--hz", type=float, default=10.0, help="screen refresh rate")
  ap.add_argument("--duration", type=float, default=0.0, help="optional max run time in seconds; 0 means infinite")
  ap.add_argument("--serial", default="", help="optional picoflex USB serial")
  args = ap.parse_args()

  period = 1.0 / max(args.hz, 0.2)
  dev = open_picoflex_device(args.serial)
  try:
    configure_can_bitrate(dev, args.bus, args.speed_kbps)
    state = LiveCanState()
    last_raw770: int | None = None
    health0 = read_can_health(dev)
    start = time.monotonic()
    last_print = 0.0
    print(f"# monitor serial={dev.serial} bus={args.bus} speed={args.speed_kbps}kbps hz={args.hz:.1f}")
    print("# scale (raw770 - 32748) * 0.03540")
    while True:
      state, reads, raw770 = poll_live_steer770_raw(dev, state, timeout_ms=max(1, int(period * 1000)))
      if raw770 is not None:
        last_raw770 = raw770
      now = time.monotonic()
      if now - last_print >= period:
        health = read_can_health(dev)
        angle = state.steer770_deg
        angle_txt = "None" if angle is None else f"{angle:+8.2f} deg"
        raw_txt = "None" if last_raw770 is None else f"{last_raw770:5d}"
        print(
          f"t={now - start:7.2f}s  raw770={raw_txt}  steer770={angle_txt}  "
          f"reads={reads:2d}  rx+={health.total_rx_cnt - health0.total_rx_cnt:6d}  "
          f"lost+={health.total_rx_lost_cnt - health0.total_rx_lost_cnt:4d}"
        )
        last_print = now
      if args.duration > 0.0 and now - start >= args.duration:
        break
  finally:
    dev.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
