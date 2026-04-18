#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from pathlib import Path

import usb1

from tools.bmw_i3_direct_lat_sweep import (
  USB_READ_EP,
  USB_WRITE_EP,
  open_picoflex_device,
  pack_override,
  unpack_flexray_records,
)


SUPPORTED_FW_TARGETS = {0x15, 0x38, 0x44}


@dataclass(frozen=True)
class Candidate:
  name: str
  frame_id: int
  source: int
  offset: int
  signed: bool
  gain_deg_per_raw: float
  base: int
  valid_cycles: tuple[int, ...] | None = None
  ff_tail_from: int | None = None


CANDIDATES = {
  # Strongest local angle-request candidate. Requires a firmware rule before it
  # can actually fire; this host script only prepares/sends the raw override.
  "0x15_b7_8": Candidate(
    name="0x15_b7_8",
    frame_id=0x15,
    source=14,
    offset=7,
    signed=False,
    gain_deg_per_raw=0.0155,
    base=0x01,
    valid_cycles=(0, 2),
    ff_tail_from=9,
  ),
  # Strong angle-like copy/support frame. Not the preferred command target, but
  # useful for one-at-a-time negative/positive tests if firmware rule is added.
  "0x38_b11_12": Candidate(
    name="0x38_b11_12",
    frame_id=0x38,
    source=24,
    offset=11,
    signed=False,
    gain_deg_per_raw=0.0179,
    base=0x00,
  ),
  # Current firmware already accepts raw 0x44 overrides. This field was strong
  # on route 59 and weak/inconsistent on route 58, so keep the default delta low.
  "0x44_b12_13": Candidate(
    name="0x44_b12_13",
    frame_id=0x44,
    source=24,
    offset=12,
    signed=True,
    gain_deg_per_raw=0.000238,
    base=0x00,
  ),
  # Previously selected local 0x44 torque/control field, inverse correlation.
  "0x44_b13_14": Candidate(
    name="0x44_b13_14",
    frame_id=0x44,
    source=24,
    offset=13,
    signed=True,
    gain_deg_per_raw=-0.0000625,
    base=0x00,
  ),
}


@dataclass
class LiveState:
  overflow: bytes = b""
  payload: bytes = b""
  cycle: int = -1
  raw: int = 0
  source: int = -1
  steer33_deg: float | None = None
  steer33_raw: int | None = None
  angle38_raw: int | None = None
  last_rx_monotonic: float = 0.0


def eps33_deg(payload: bytes) -> tuple[float, int] | None:
  if len(payload) < 5 or (payload[0] & 0x3) not in (0, 2):
    return None
  raw = payload[3] | (payload[4] << 8)
  if raw < 20000 or raw > 45000:
    return None
  return raw * 0.042420980556 - 1390.727380850223, raw


def read_raw(payload: bytes, off: int, signed: bool) -> int:
  raw = payload[off] | (payload[off + 1] << 8)
  if signed and raw >= 0x8000:
    raw -= 0x10000
  return raw


def write_raw(payload: bytes, off: int, signed: bool, value: int) -> bytes:
  lo = -32768 if signed else 0
  hi = 32767 if signed else 65535
  raw = max(lo, min(hi, int(value)))
  if signed and raw < 0:
    raw += 0x10000
  out = bytearray(payload)
  out[off] = raw & 0xFF
  out[off + 1] = (raw >> 8) & 0xFF
  return bytes(out)


def valid_candidate_payload(candidate: Candidate, cycle: int, payload: bytes) -> bool:
  if len(payload) < max(16, candidate.offset + 2):
    return False
  if candidate.valid_cycles is not None and (payload[0] & 0x3) not in candidate.valid_cycles:
    return False
  if candidate.ff_tail_from is not None and payload[candidate.ff_tail_from:16] != b"\xff" * (16 - candidate.ff_tail_from):
    return False
  return True


def poll_candidate(dev, candidate: Candidate, state: LiveState, timeout_ms: int = 25) -> LiveState:
  try:
    raw = bytes(dev.handle.bulkRead(USB_READ_EP, 16384, timeout=timeout_ms))
  except usb1.USBErrorTimeout:
    return state

  records, overflow = unpack_flexray_records(state.overflow + raw)
  state.overflow = overflow
  for frame_id, source, cycle, payload in records:
    if frame_id == 0x33 and source == 24:
      steer = eps33_deg(payload)
      if steer is not None:
        state.steer33_deg, state.steer33_raw = steer
        state.last_rx_monotonic = time.monotonic()

    if frame_id == 0x38 and source == 24 and len(payload) >= 13:
      state.angle38_raw = payload[11] | (payload[12] << 8)
      state.last_rx_monotonic = time.monotonic()

    if frame_id != candidate.frame_id or source != candidate.source:
      continue
    if not valid_candidate_payload(candidate, cycle, payload):
      continue
    state.payload = bytes(payload[:16])
    state.cycle = cycle
    state.source = source
    state.raw = read_raw(state.payload, candidate.offset, candidate.signed)
    state.last_rx_monotonic = time.monotonic()
  return state


def wait_for_template(dev, candidate: Candidate, timeout_s: float) -> LiveState:
  state = LiveState()
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    state = poll_candidate(dev, candidate, state, timeout_ms=100)
    if state.payload:
      return state
  raise TimeoutError(f"timed out waiting for live {candidate.name} template")


def triangle_profile(t_s: float, rate_deg_s: float, max_delta_deg: float) -> float:
  t1 = abs(max_delta_deg) / max(rate_deg_s, 1e-6)
  t2 = 2.0 * abs(max_delta_deg) / max(rate_deg_s, 1e-6)
  if t_s <= t1:
    return t_s * rate_deg_s
  t_s -= t1
  if t_s <= t2:
    return max_delta_deg - t_s * rate_deg_s
  t_s -= t2
  if t_s <= t1:
    return -max_delta_deg + t_s * rate_deg_s
  return 0.0


def corr(xs: list[float], ys: list[float]) -> float | None:
  n = len(xs)
  if n < 5 or n != len(ys):
    return None
  mx = sum(xs) / n
  my = sum(ys) / n
  vx = sum((x - mx) ** 2 for x in xs)
  vy = sum((y - my) ** 2 for y in ys)
  if vx <= 1e-12 or vy <= 1e-12:
    return None
  return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (vx * vy) ** 0.5


def summarize(rows: list[dict[str, float | int | str]]) -> None:
  steer = [float(r["steer33_deg"]) for r in rows if r["steer33_deg"] != ""]
  raw_delta = [float(r["raw_delta"]) for r in rows if r["steer33_deg"] != ""]
  steer_for_corr = [float(r["steer33_deg"]) for r in rows if r["steer33_deg"] != ""]
  if not rows:
    print("summary: no rows captured")
    return
  if steer:
    print(
      f"summary: steer33_min={min(steer):+.3f}deg steer33_max={max(steer):+.3f}deg "
      f"steer33_span={max(steer) - min(steer):.3f}deg"
    )
    c = corr(raw_delta, steer_for_corr)
    print(f"summary: corr(raw_delta, steer33_deg)={(c if c is not None else float('nan')):+.4f}")
  else:
    print("summary: no valid 0x33 steering feedback captured")


def main() -> int:
  ap = argparse.ArgumentParser(description="BMW i3 one-at-a-time FlexRay angle candidate injector")
  ap.add_argument("--candidate", choices=sorted(CANDIDATES), required=True)
  ap.add_argument("--serial", default="")
  ap.add_argument("--rate-deg-per-sec", type=float, default=3.0)
  ap.add_argument("--max-delta-deg", type=float, default=2.0)
  ap.add_argument("--max-raw-delta", type=int, default=200)
  ap.add_argument("--base", type=lambda x: int(x, 0), default=None)
  ap.add_argument("--duration", type=float, default=0.0, help="0 means one full 0 -> +max -> -max -> 0 triangle")
  ap.add_argument("--log", type=Path, default=None, help="optional CSV log path")
  ap.add_argument("--run", action="store_true", help="actually transmit; default is dry-run")
  args = ap.parse_args()

  candidate = CANDIDATES[args.candidate]
  base = candidate.base if args.base is None else args.base & 0xFF
  if candidate.frame_id not in SUPPORTED_FW_TARGETS:
    print(f"WARNING: firmware rule for target {candidate.frame_id:#x} is not enabled yet; packets may be rejected/ignored.")
  if not args.run:
    print("dry-run only; add --run to transmit")

  total = args.duration
  if total <= 0.0:
    total = 4.0 * abs(args.max_delta_deg) / max(args.rate_deg_per_sec, 1e-6)

  dev = open_picoflex_device(args.serial)
  try:
    print(f"connected picoflex: {dev.serial}")
    state = wait_for_template(dev, candidate, timeout_s=3.0)
    center_raw = state.raw
    print(
      f"candidate={candidate.name} frame={candidate.frame_id:#x} src={candidate.source} "
      f"cycle={state.cycle} raw_center={center_raw} template={state.payload.hex()}"
    )

    start = time.monotonic()
    sent = 0
    rows: list[dict[str, float | int | str]] = []
    last_sig: tuple[int, bytes, int] | None = None
    while True:
      now = time.monotonic()
      t_s = now - start
      if t_s > total:
        break

      state = poll_candidate(dev, candidate, state, timeout_ms=25)
      if not state.payload:
        continue

      delta_deg = triangle_profile(t_s, args.rate_deg_per_sec, args.max_delta_deg)
      raw_delta = int(round(delta_deg / candidate.gain_deg_per_raw)) if abs(candidate.gain_deg_per_raw) > 1e-9 else 0
      raw_delta = max(-args.max_raw_delta, min(args.max_raw_delta, raw_delta))
      target_raw = center_raw + raw_delta
      payload = write_raw(state.payload, candidate.offset, candidate.signed, target_raw)
      sig = (state.cycle, payload, target_raw)
      if sig == last_sig:
        continue
      last_sig = sig

      pkt = pack_override(candidate.frame_id, base, bytes([base]) + payload)
      print(
        f"t={t_s:6.2f}s cycle={state.cycle:02d} stock_raw={state.raw:7d} "
        f"delta_deg={delta_deg:+6.2f} raw_delta={raw_delta:+5d} target_raw={target_raw:7d} "
        f"steer33={(state.steer33_deg if state.steer33_deg is not None else float('nan')):+7.3f} tx={payload.hex()}"
      )
      if args.run:
        dev.handle.bulkWrite(USB_WRITE_EP, pkt, timeout=10)
      rows.append({
        "t_s": round(t_s, 6),
        "candidate": candidate.name,
        "cycle": state.cycle,
        "stock_raw": state.raw,
        "raw_delta": raw_delta,
        "target_raw": target_raw,
        "delta_deg_cmd": round(delta_deg, 6),
        "steer33_deg": "" if state.steer33_deg is None else round(state.steer33_deg, 6),
        "steer33_raw": "" if state.steer33_raw is None else state.steer33_raw,
        "angle38_raw": "" if state.angle38_raw is None else state.angle38_raw,
        "tx_hex": payload.hex(),
      })
      sent += 1

    print(f"END candidate={candidate.name} sent={sent}")
    if args.log is not None:
      args.log.parent.mkdir(parents=True, exist_ok=True)
      with args.log.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["t_s"])
        writer.writeheader()
        writer.writerows(rows)
      print(f"log={args.log}")
    summarize(rows)
    return 0
  finally:
    dev.close()


if __name__ == "__main__":
  raise SystemExit(main())
