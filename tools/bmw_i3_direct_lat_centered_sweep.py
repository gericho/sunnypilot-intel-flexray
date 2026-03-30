#!/usr/bin/env python3
import argparse
import time

from tools.bmw_i3_direct_lat_sweep import (
  open_picoflex_device,
  recv_until_lat_ready,
  poll_lat_state,
  target_b1_for_angle,
  build_frame72,
  build_frame96,
  send_lat_override_pair,
)


def profile_angle(t_s: float, rate_deg_s: float) -> float:
  # 0 -> +30, +30 -> -30, -30 -> 0
  t1 = 30.0 / rate_deg_s
  t2 = 60.0 / rate_deg_s
  t3 = 30.0 / rate_deg_s
  if t_s <= t1:
    return t_s * rate_deg_s
  t_s -= t1
  if t_s <= t2:
    return 30.0 - t_s * rate_deg_s
  t_s -= t2
  if t_s <= t3:
    return -30.0 + t_s * rate_deg_s
  return 0.0


def main() -> int:
  ap = argparse.ArgumentParser(description='BMW i3 direct lateral centered sweep: +30 / -30 / 0')
  ap.add_argument('--serial', default='')
  ap.add_argument('--rate-deg-per-sec', type=float, default=1.0)
  ap.add_argument('--hz', type=float, default=20.0)
  ap.add_argument('--max-b1-delta', type=int, default=48)
  ap.add_argument('--bus-idle-timeout', type=float, default=0.5)
  ap.add_argument('--run', action='store_true')
  args = ap.parse_args()

  dev = open_picoflex_device(args.serial)
  try:
    print('connected picoflex:', dev.serial)
    st = recv_until_lat_ready(dev)
    print(f'live lat: phase={st.phase} b1={st.b1} b2={st.b2} b3={st.b3} cycle={st.cycle}')

    total = (30.0 + 60.0 + 30.0) / max(args.rate_deg_per_sec, 1e-6)
    period = 1.0 / max(args.hz, 1.0)
    steps = int(total / period) + 1
    overflow = b''
    cnt = 0
    start = time.monotonic()

    print('profile: 0 -> +30 deg, +30 -> -30 deg, -30 -> 0 deg @ %.2f deg/s' % args.rate_deg_per_sec)
    if not args.run:
      print('dry-run only; add --run to transmit')

    for i in range(steps):
      st, overflow = poll_lat_state(dev, st, overflow, timeout_ms=0)
      t = i * period
      angle = profile_angle(t, args.rate_deg_per_sec)
      b1 = target_b1_for_angle(st.phase, angle, st.b1, args.max_b1_delta)
      tx72 = build_frame72(st.phase, cnt)
      tx96 = build_frame96(st.phase, b1, st.b2, st.b3)
      idle = (time.monotonic() - st.last_rx_monotonic) > args.bus_idle_timeout
      print(f't={t:6.2f}s angle={angle:7.2f} phase={st.phase:3d} b1={b1:3d} b2={st.b2:3d} b3={st.b3:3d} cnt={cnt:02d} idle={int(idle)} tx72={tx72[:9].hex()} tx96={tx96[:9].hex()}')
      if args.run and not idle:
        send_lat_override_pair(dev, tx72, tx96)
      cnt = (cnt + 1) & 0x0F
      next_t = start + (i + 1) * period
      sleep_s = next_t - time.monotonic()
      if sleep_s > 0:
        time.sleep(sleep_s)
    return 0
  finally:
    dev.close()


if __name__ == '__main__':
  raise SystemExit(main())
