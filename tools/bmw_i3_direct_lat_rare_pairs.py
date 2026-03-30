#!/usr/bin/env python3
import argparse
import time

from tools.bmw_i3_direct_lat_sweep import (
  LatState,
  open_picoflex_device,
  pack_override,
  unpack_flexray_records,
  USB_WRITE_EP,
  USB_READ_EP,
)
from tools.bmw_i3_rlog_raw_inject import (
  LiveCanState,
  configure_can_bitrate,
  read_can_health,
  unpack_can_buffer,
)

PAIR_MAP = {
  'p1': (
    bytes.fromhex('29fff4ffffffffffe0ffffffffffffffff'),
    bytes.fromhex('343ff3e0ffffffffff'),
  ),
  'p2': (
    bytes.fromhex('21fffbffffffffffe0ffffffffffffffff'),
    bytes.fromhex('3433f121ffffffffff'),
  ),
  'p3': (
    bytes.fromhex('37fff1ffffffffffe0ffffffffffffffff'),
    bytes.fromhex('04edfbe0ffffffffff'),
  ),
}

POSITIVE_96_PATTERNS = (
  "e0f721",
  "bcf821",
  "33f121",
  "d4f221",
  "89f321",
)

NEGATIVE_96_PATTERNS = (
  "5bfb21",
  "d5fc21",
  "88fd21",
  "6ffe21",
)


def scale_770_live(raw: int) -> float:
  return (raw - 32748) * 0.03540


def classify_flex_context(frame131: bytes | None, frame135: bytes | None, frame96: bytes | None,
                          frame267: bytes | None, frame269: bytes | None) -> str:
  if frame131 is None and frame135 is None and frame96 is None and frame267 is None and frame269 is None:
    return "no-data"

  if (frame131 in (None, b"\x00" * len(frame131 or b""))) and (frame135 in (None, b"\x00" * len(frame135 or b""))):
    return "idle"

  p131 = frame131.hex() if frame131 else ""
  p135 = frame135.hex() if frame135 else ""
  manual_135 = "22e0e188" in p135
  acc_135 = "2228e260" in p135 and p135.endswith("a205")
  acc_family_135 = (
    "20e0e240" in p135 or
    "28e268" in p135 or
    "29e268" in p135 or
    ("2228e260" in p135 and not p135.endswith("a205"))
  )
  manual_131 = p131.endswith("bb8302ffff") or p131.endswith("ba8302ffff") or p131.endswith("b98302ffff")
  tja_131 = p131.endswith("00000effff") or p131.endswith("7f8002ffff") or p131.endswith("7d8002ffff") or p131.endswith("7c8002ffff")
  authority_135 = ("20e0e2403206" in p135) or ("2228e2604206" in p135)
  fr_context = frame267 is not None or frame269 is not None or frame96 is not None

  if manual_131 or manual_135:
    return "manual"
  if authority_135 and tja_131 and fr_context:
    return "authority_like"
  if tja_131 and (acc_135 or acc_family_135):
    return "acc_family"
  if tja_131 or acc_135 or acc_family_135:
    return "acc_family"
  if frame96 is not None:
    return "acc_family"
  return "mixed"


def poll_flex_state(dev, st: LatState, overflow: bytes, frames: dict[int, bytes], frame_ts: dict[int, float],
                    timeout_ms: int = 0) -> tuple[LatState, bytes, dict[int, bytes], dict[int, float]]:
  import usb1

  try:
    raw = bytes(dev.handle.bulkRead(USB_READ_EP, 16384, timeout=timeout_ms))
  except usb1.USBErrorTimeout:
    return st, overflow, frames, frame_ts

  records, overflow = unpack_flexray_records(overflow + raw)
  now = time.monotonic()
  out_frames = dict(frames)
  out_ts = dict(frame_ts)
  for frame_id, source, cycle, payload in records:
    if source != 0:
      continue
    if frame_id in (72, 96, 131, 135, 267, 269):
      out_frames[frame_id] = payload
      out_ts[frame_id] = now
    if frame_id == 72 and len(payload) >= 9:
      st.cycle = cycle
      st.seen_72 = True
      st.last_rx_monotonic = now
    elif frame_id == 96 and len(payload) >= 4:
      st.cycle = cycle
      st.phase = payload[0]
      st.b1 = payload[1]
      st.b2 = payload[2]
      st.b3 = payload[3]
      st.seen_96 = True
      st.last_rx_monotonic = now
  return st, overflow, out_frames, out_ts


def poll_live_steer770_raw(dev, state: LiveCanState, timeout_ms: int = 0) -> tuple[LiveCanState, int | None]:
  import usb1

  try:
    raw = bytes(dev.handle.bulkRead(0x82, 16384, timeout=timeout_ms))
  except usb1.USBErrorTimeout:
    return state, None

  steer770 = state.steer770_deg
  steer770_raw = None
  records, overflow = unpack_can_buffer(state.overflow + raw)
  for address, payload, bus in records:
    if bus == 2 and address == 770 and len(payload) >= 4:
      steer770_raw = payload[2] | (payload[3] << 8)
      steer770 = scale_770_live(steer770_raw)
  return LiveCanState(steer770_deg=steer770, overflow=overflow), steer770_raw


def wait_for_live_770(dev, timeout_s: float = 3.0) -> tuple[LiveCanState, int]:
  state = LiveCanState()
  deadline = time.monotonic() + timeout_s
  last_raw = None
  while time.monotonic() < deadline:
    state, raw = poll_live_steer770_raw(dev, state, timeout_ms=100)
    if raw is not None:
      last_raw = raw
    if state.steer770_deg is not None and last_raw is not None:
      return state, last_raw
  raise TimeoutError("timed out waiting for live 770 feedback")


def wait_for_healthy_lat(dev, timeout_s: float = 3.0, require_authority_like: bool = False) -> tuple[LatState, bytes, dict[int, bytes], dict[int, float], str]:
  st = LatState()
  overflow = b""
  frames: dict[int, bytes] = {}
  frame_ts: dict[int, float] = {}
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    st, overflow, frames, frame_ts = poll_flex_state(dev, st, overflow, frames, frame_ts, timeout_ms=100)
    age_ms = (time.monotonic() - st.last_rx_monotonic) * 1000.0
    ctx = classify_flex_context(frames.get(131), frames.get(135), frames.get(96), frames.get(267), frames.get(269))
    if st.phase != 255 and age_ms < 150.0:
      if not require_authority_like or ctx == "authority_like":
        return st, overflow, frames, frame_ts, ctx
  raise TimeoutError("timed out waiting for healthy live 72/96 phase")


def send_pair(dev, tx72: bytes, tx96: bytes, base: int, tx135: bytes | None = None) -> None:
  pkt72 = pack_override(72, base, bytes([base]) + tx72[:9])
  pkt96 = pack_override(96, base, bytes([base]) + tx96[:9])
  blob = pkt72 + pkt96
  if tx135 is not None:
    blob += pack_override(135, base, bytes([base]) + tx135[:9])
  dev.handle.bulkWrite(USB_WRITE_EP, blob, timeout=10)


def parse_prefixes(args_prefixes: list[str], family: str) -> tuple[str, ...]:
  vals: list[str] = []
  if family == "positive":
    vals.extend(POSITIVE_96_PATTERNS)
  elif family == "negative":
    vals.extend(NEGATIVE_96_PATTERNS)
  elif family == "both":
    vals.extend(POSITIVE_96_PATTERNS)
    vals.extend(NEGATIVE_96_PATTERNS)
  for p in args_prefixes:
    norm = p.strip().lower()
    if not norm:
      continue
    if len(norm) % 2 != 0:
      raise ValueError(f"invalid odd-length hex prefix: {p}")
    vals.append(norm)
  dedup: list[str] = []
  for v in vals:
    if v not in dedup:
      dedup.append(v)
  return tuple(dedup)


def live96_matches(live96: bytes | None, patterns: tuple[str, ...]) -> bool:
  if live96 is None:
    return False
  hx = live96.hex()
  if len(hx) < 6:
    return False
  head3 = hx[:6]
  body3 = hx[2:8] if len(hx) >= 8 else ""
  return any(head3 == p or body3 == p for p in patterns)


def frame135_family(frame135: bytes | None) -> str:
  if frame135 is None:
    return "none"
  hx = frame135.hex()
  if "22e0e188" in hx:
    return "manual"
  if "2228e260" in hx and hx.endswith("a205"):
    return "acc_only"
  if "20e0e2403206" in hx or "2228e2604206" in hx:
    return "tja_strong"
  if "20e0e240" in hx or "28e268" in hx or "29e268" in hx or ("2228e260" in hx and not hx.endswith("a205")):
    return "acc_family"
  return "other"


def make_tja_strong_135(frame135: bytes | None) -> bytes | None:
  if frame135 is None:
    return None
  raw = bytes(frame135)
  if len(raw) >= 9:
    return raw[:3] + bytes.fromhex("20e0e2403206")
  if len(raw) == 8:
    return raw[:2] + bytes.fromhex("20e0e2403206")
  return None


def main() -> int:
  ap = argparse.ArgumentParser(description='Send rare 24-only 72/96 lateral pairs')
  ap.add_argument('--serial', default='')
  ap.add_argument('--pair', choices=sorted(PAIR_MAP.keys()) + ['all'], default='all')
  ap.add_argument('--delta-b1', type=int, default=0, help='override pair mode: perturb live 96 byte1 by this amount')
  ap.add_argument('--delta-b2', type=int, default=0, help='override pair mode: perturb live 96 byte2 by this amount')
  ap.add_argument('--seconds', type=float, default=4.0)
  ap.add_argument('--hz', type=float, default=10.0)
  ap.add_argument('--bus', type=int, default=2)
  ap.add_argument('--speed-kbps', type=int, default=500)
  ap.add_argument('--stale-ms', type=float, default=250.0)
  ap.add_argument('--feedback-timeout', type=float, default=3.0)
  ap.add_argument('--observe-ms', type=float, default=600.0)
  ap.add_argument('--wait-for-family-s', type=float, default=0.0, help='wait up to this many seconds for a required 96 family before aborting')
  ap.add_argument('--require-authority-like', action='store_true', help='only send when FlexRay context is authority_like')
  ap.add_argument('--require-135-family', choices=['acc_family', 'tja_strong'], default='', help='only send when live 135 is in the selected family')
  ap.add_argument('--force-135-tja-strong', action='store_true', help='send 135 with a TJA-strong suffix while preserving the live prefix')
  ap.add_argument('--require-96-family', choices=['positive', 'negative', 'both'], default='', help='only send when live 96 matches a known TJA family')
  ap.add_argument('--require-96-prefix', action='append', default=[], help='extra hex prefix to require on live 96; may be passed multiple times')
  ap.add_argument('--use-live-72', action='store_true', default=True, help='use the live 72 payload as the base template instead of a synthetic placeholder')
  ap.add_argument('--print-health', action='store_true')
  ap.add_argument('--run', action='store_true')
  args = ap.parse_args()

  use_live_delta = (args.delta_b1 != 0) or (args.delta_b2 != 0)
  required_96_prefixes = parse_prefixes(args.require_96_prefix, args.require_96_family)
  order = ['live_delta'] if use_live_delta else (['p1', 'p2', 'p3'] if args.pair == 'all' else [args.pair])
  dev = open_picoflex_device(args.serial)
  try:
    print('connected picoflex:', dev.serial)
    configure_can_bitrate(dev, args.bus, args.speed_kbps)
    if args.print_health:
      health = read_can_health(dev)
      print(
        f"can bus={args.bus} speed={health.can_speed}kbps "
        f"rx={health.total_rx_cnt} lost={health.total_rx_lost_cnt} err={health.total_error_cnt}"
      )
    st, overflow, frames, frame_ts, ctx = wait_for_healthy_lat(
      dev, timeout_s=args.feedback_timeout, require_authority_like=args.require_authority_like
    )
    can_state, raw770 = wait_for_live_770(dev, timeout_s=args.feedback_timeout)
    baseline_steer = can_state.steer770_deg if can_state.steer770_deg is not None else 0.0
    print(
      f'live lat: ctx={ctx} phase={st.phase} b1={st.b1} b2={st.b2} b3={st.b3} cycle={st.cycle} '
      f'raw770={raw770} steer770={baseline_steer:+.2f}'
    )
    if required_96_prefixes:
      print('require 96 prefixes:', ', '.join(required_96_prefixes))
    period = 1.0 / max(args.hz, 1.0)
    for name in order:
      if name == 'live_delta':
        live72 = frames.get(72)
        if args.use_live_72 and live72 is not None and len(live72) >= 9:
          tx72_raw = bytearray(live72[:9])
        else:
          tx72_raw = bytearray([0x00, 0xFF, 0xF0 | (st.cycle & 0xF), 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xE0])
        tx96_raw = bytearray([st.phase & 0xFF, st.b1 & 0xFF, st.b2 & 0xFF, st.b3 & 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        tx135_raw = make_tja_strong_135(frames.get(135)) if args.force_135_tja_strong else None
        tx96_raw[1] = max(0, min(255, tx96_raw[1] + args.delta_b1))
        tx96_raw[2] = max(0, min(255, tx96_raw[2] + args.delta_b2))
        print(
          f'PAIR live_delta phase={st.phase} b1={st.b1}->{tx96_raw[1]} '
          f'b2={st.b2}->{tx96_raw[2]} b3={st.b3} '
          f'raw72={bytes(tx72_raw[:9]).hex()} raw96={bytes(tx96_raw[:9]).hex()} '
          f'raw135={(tx135_raw.hex() if tx135_raw is not None else "None")}'
        )
      else:
        tx72_raw, tx96_raw = PAIR_MAP[name]
        tx135_raw = None
        print(f'PAIR {name} raw72={tx72_raw[:9].hex()} raw96={tx96_raw[:9].hex()}')
      start = time.monotonic()
      steps = max(1, int(round(args.seconds / period)))
      for i in range(steps):
        st, overflow, frames, frame_ts = poll_flex_state(dev, st, overflow, frames, frame_ts, timeout_ms=0)
        can_state, raw770 = poll_live_steer770_raw(dev, can_state, timeout_ms=0)
        age_ms = (time.monotonic() - st.last_rx_monotonic) * 1000.0
        ctx = classify_flex_context(frames.get(131), frames.get(135), frames.get(96), frames.get(267), frames.get(269))
        live96 = frames.get(96)
        live96_hex = live96.hex() if live96 else ""
        fam135 = frame135_family(frames.get(135))
        if st.phase == 255:
          print(f'  abort t={i*period:4.2f}s phase=255 raw770={raw770} steer770={can_state.steer770_deg}')
          return 2
        if st.last_rx_monotonic <= 0.0 or age_ms > args.stale_ms:
          print(f'  abort t={i*period:4.2f}s stale72_96 age_ms={age_ms:.1f} phase={st.phase}')
          return 3
        if args.require_authority_like and ctx != "authority_like":
          print(f'  abort t={i*period:4.2f}s ctx={ctx} phase={st.phase} raw770={raw770} steer770={can_state.steer770_deg}')
          return 4
        if args.require_135_family and fam135 != args.require_135_family:
          if args.wait_for_family_s > 0:
            wait_deadline = time.monotonic() + args.wait_for_family_s
            matched_135 = False
            last135 = fam135
            while time.monotonic() < wait_deadline:
              st, overflow, frames, frame_ts = poll_flex_state(dev, st, overflow, frames, frame_ts, timeout_ms=100)
              can_state, raw770 = poll_live_steer770_raw(dev, can_state, timeout_ms=0)
              age_ms = (time.monotonic() - st.last_rx_monotonic) * 1000.0
              ctx = classify_flex_context(frames.get(131), frames.get(135), frames.get(96), frames.get(267), frames.get(269))
              live96 = frames.get(96)
              live96_hex = live96.hex() if live96 else ""
              fam135 = frame135_family(frames.get(135))
              last135 = fam135
              if st.phase == 255 or st.last_rx_monotonic <= 0.0 or age_ms > args.stale_ms:
                print(f'  abort wait stale/phase255 age_ms={age_ms:.1f} phase={st.phase} 135={last135}')
                return 7
              if args.require_authority_like and ctx != "authority_like":
                print(f'  abort wait ctx={ctx} phase={st.phase} 135={last135}')
                return 8
              if fam135 == args.require_135_family:
                matched_135 = True
                print(f'  matched 135 family after wait: ctx={ctx} phase={st.phase} 135={frames.get(135).hex() if frames.get(135) else None}')
                break
            if not matched_135:
              print(f'  abort t={i*period:4.2f}s 135={last135} not-in-required-family-after-wait')
              return 7
          else:
            print(f'  abort t={i*period:4.2f}s 135={fam135} not-in-required-family')
            return 7
        if required_96_prefixes and not live96_matches(live96, required_96_prefixes):
          if args.wait_for_family_s > 0:
            wait_deadline = time.monotonic() + args.wait_for_family_s
            matched = False
            last_seen = live96_hex or "None"
            while time.monotonic() < wait_deadline:
              st, overflow, frames, frame_ts = poll_flex_state(dev, st, overflow, frames, frame_ts, timeout_ms=100)
              can_state, raw770 = poll_live_steer770_raw(dev, can_state, timeout_ms=0)
              age_ms = (time.monotonic() - st.last_rx_monotonic) * 1000.0
              ctx = classify_flex_context(frames.get(131), frames.get(135), frames.get(96), frames.get(267), frames.get(269))
              live96 = frames.get(96)
              live96_hex = live96.hex() if live96 else ""
              last_seen = live96_hex or "None"
              if st.phase == 255 or st.last_rx_monotonic <= 0.0 or age_ms > args.stale_ms:
                print(f'  abort wait stale/phase255 age_ms={age_ms:.1f} phase={st.phase} 96={last_seen}')
                return 5
              if args.require_authority_like and ctx != "authority_like":
                print(f'  abort wait ctx={ctx} phase={st.phase} 96={last_seen}')
                return 6
              if live96_matches(live96, required_96_prefixes):
                matched = True
                print(f'  matched family after wait: ctx={ctx} phase={st.phase} 96={live96_hex}')
                if name == 'live_delta':
                  live72 = frames.get(72)
                  if args.use_live_72 and live72 is not None and len(live72) >= 9:
                    tx72_raw = bytearray(live72[:9])
                  else:
                    tx72_raw = bytearray([0x00, 0xFF, 0xF0 | (st.cycle & 0xF), 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xE0])
                  tx96_raw = bytearray([st.phase & 0xFF, st.b1 & 0xFF, st.b2 & 0xFF, st.b3 & 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
                  tx135_raw = make_tja_strong_135(frames.get(135)) if args.force_135_tja_strong else None
                  tx96_raw[1] = max(0, min(255, tx96_raw[1] + args.delta_b1))
                  tx96_raw[2] = max(0, min(255, tx96_raw[2] + args.delta_b2))
                  print(
                    f'  refreshed live_delta phase={st.phase} b1={st.b1}->{tx96_raw[1]} '
                    f'b2={st.b2}->{tx96_raw[2]} b3={st.b3} '
                    f'raw72={bytes(tx72_raw[:9]).hex()} raw96={bytes(tx96_raw[:9]).hex()} '
                    f'raw135={(tx135_raw.hex() if tx135_raw is not None else "None")}'
                  )
                break
            if not matched:
              print(f'  abort t={i*period:4.2f}s 96={last_seen} not-in-required-family-after-wait')
              return 5
          else:
            print(f'  abort t={i*period:4.2f}s 96={live96_hex or "None"} not-in-required-family')
            return 5
        tx72 = bytearray(tx72_raw)
        tx96 = bytearray(tx96_raw)
        tx72[0] = st.phase & 0xFF
        tx72[2] = (tx72[2] & 0xF0) | (st.cycle & 0x0F)
        tx96[0] = st.phase & 0xFF
        delta770 = None if can_state.steer770_deg is None else can_state.steer770_deg - baseline_steer
        delta_txt = 'None' if delta770 is None else f'{delta770:+7.2f}'
        steer_txt = 'None' if can_state.steer770_deg is None else f'{can_state.steer770_deg:+7.2f}'
        raw_txt = 'None' if raw770 is None else str(raw770)
        print(
          f'  t={i*period:4.2f}s ctx={ctx:14s} phase={st.phase:3d} age={age_ms:5.1f}ms '
          f'raw770={raw_txt:>5} steer770={steer_txt} d770={delta_txt} '
          f'tx72={bytes(tx72[:9]).hex()} tx96={bytes(tx96[:9]).hex()} '
          f'tx135={(tx135_raw.hex() if tx135_raw is not None else "None")}'
        )
        if args.run:
          send_pair(dev, bytes(tx72), bytes(tx96), base=st.phase & 0xFF, tx135=tx135_raw)
        next_t = start + (i + 1) * period
        sleep_s = next_t - time.monotonic()
        if sleep_s > 0:
          time.sleep(sleep_s)
      observe_deadline = time.monotonic() + max(args.observe_ms, 0.0) / 1000.0
      while time.monotonic() < observe_deadline:
        can_state, raw770 = poll_live_steer770_raw(dev, can_state, timeout_ms=25)
      delta770 = None if can_state.steer770_deg is None else can_state.steer770_deg - baseline_steer
      delta_txt = 'None' if delta770 is None else f'{delta770:+.2f}'
      print(f'END {name} raw770={raw770} steer770={can_state.steer770_deg} d770={delta_txt}')
      time.sleep(0.5)
    return 0
  finally:
    dev.close()


if __name__ == '__main__':
  raise SystemExit(main())
