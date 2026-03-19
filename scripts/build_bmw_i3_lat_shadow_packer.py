#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Optional

from tools.lib.logreader import LogReader


LABELED_ROUTES = {
  "e9": {
    "fn": "/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst",
    "windows": [
      ("right", 25, 28), ("left", 29, 34), ("right", 40, 44),
      ("right", 66, 67), ("left", 69, 70),
    ],
  },
  "ea": {
    "fn": "/home/gericho/.comma/media/0/realdata/000000ea--291dc1d088--0/rlog.zst",
    "windows": [
      ("right", 37, 41), ("left", 59, 60), ("right", 66, 67), ("left", 69, 70),
      ("right", 73, 74), ("left", 77, 78), ("right", 101, 106),
    ],
  },
  "eb": {
    "fn": "/home/gericho/.comma/media/0/realdata/000000eb--41f9ac2c70--0/rlog.zst",
    "windows": [("right", 41, 42), ("left", 43, 44), ("left", 86, 87)],
  },
}

PHASE_THRESHOLDS = {
  60: 112.083,
  24: 80.833,
  8: 149.5,
}


@dataclass
class Sample:
  route: str
  label: str
  phase: int
  d72: bytes
  d96: bytes


@dataclass
class PhaseProfile:
  phase: int
  threshold: float
  b1_left: int
  b1_right: int
  b2_left: int
  b2_right: int
  b3: int
  b4: int
  b8: int
  magnitude_confidence: str


def label_for_time(t: float, windows: list[tuple[str, float, float]]) -> Optional[str]:
  for label, start, end in windows:
    if start <= t < end:
      return label
  return None


def collect_labeled_samples() -> list[Sample]:
  out: list[Sample] = []
  for route_name, cfg in LABELED_ROUTES.items():
    fn = Path(cfg["fn"])
    if not fn.exists():
      continue
    route_start = None
    last72 = None
    for evt in LogReader(str(fn)):
      if route_start is None:
        route_start = evt.logMonoTime
      t = (evt.logMonoTime - route_start) / 1e9
      if evt.which() != "can":
        continue
      label = label_for_time(t, cfg["windows"])
      for c in evt.can:
        d = bytes(c.dat)
        if c.src == 0 and c.address == 72 and len(d) >= 9:
          last72 = (t, d)
        elif label is not None and c.src == 0 and c.address == 96 and len(d) >= 9 and last72 is not None:
          if abs(last72[0] - t) > 0.03:
            continue
          d72 = last72[1]
          if d72[0] != d[0]:
            continue
          out.append(Sample(route_name, label, d[0], d72, d))
  return out


def build_phase_profiles(samples: list[Sample]) -> dict[int, PhaseProfile]:
  dyn: dict[int, dict[str, dict[str, list[int]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
  consts: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
  for s in samples:
    dyn[s.phase][s.label]["b1"].append(s.d96[1])
    dyn[s.phase][s.label]["b2"].append(s.d96[2])
    for idx in (3, 4, 8):
      consts[s.phase][idx].append(s.d96[idx])

  profiles: dict[int, PhaseProfile] = {}
  for phase, thr in PHASE_THRESHOLDS.items():
    by_dir = dyn.get(phase, {})
    if "left" not in by_dir or "right" not in by_dir:
      continue
    left_b1 = int(round(median(by_dir["left"]["b1"])))
    right_b1 = int(round(median(by_dir["right"]["b1"])))
    left_b2 = int(round(median(by_dir["left"]["b2"])))
    right_b2 = int(round(median(by_dir["right"]["b2"])))
    phase_consts = consts.get(phase, {})
    profiles[phase] = PhaseProfile(
      phase=phase,
      threshold=thr,
      b1_left=left_b1,
      b1_right=right_b1,
      b2_left=left_b2,
      b2_right=right_b2,
      b3=Counter(phase_consts.get(3, [0xE0])).most_common(1)[0][0],
      b4=Counter(phase_consts.get(4, [0xFF])).most_common(1)[0][0],
      b8=Counter(phase_consts.get(8, [0xFF])).most_common(1)[0][0],
      magnitude_confidence="high" if phase == 60 else "low",
    )
  return profiles


def clamp_u8(v: float) -> int:
  return max(0, min(255, int(round(v))))


def pack_lat96(phase: int, direction: str, mag_norm: float, profiles: dict[int, PhaseProfile]) -> Optional[bytes]:
  profile = profiles.get(phase)
  if profile is None or direction not in ("left", "right"):
    return None

  mag_norm = max(0.0, min(1.0, float(mag_norm)))
  if direction == "left":
    b1_target = profile.b1_left
    b2 = profile.b2_left
  else:
    b1_target = profile.b1_right
    b2 = profile.b2_right

  if profile.magnitude_confidence == "high":
    b1 = profile.threshold + (b1_target - profile.threshold) * mag_norm
  else:
    # Phases 24 and 8 are direction-usable but magnitude-weak. Keep the
    # direction median and do not pretend to have an analog model yet.
    b1 = float(b1_target)

  payload = bytearray(9)
  payload[0] = phase & 0xFF
  payload[1] = clamp_u8(b1)
  payload[2] = clamp_u8(b2)
  payload[3] = profile.b3 & 0xFF
  payload[4] = profile.b4 & 0xFF
  payload[5] = 0xFF
  payload[6] = 0xFF
  payload[7] = 0xFF
  payload[8] = profile.b8 & 0xFF
  return bytes(payload)


def pack_shadow_lat(phase: int, direction: str, mag_norm: float, stock72: Optional[bytes], profiles: dict[int, PhaseProfile]) -> tuple[Optional[bytes], Optional[bytes]]:
  # 72 is still best treated as stock pass-through. 96 is the current phase-local
  # payload candidate. This is a shadow packer, not a claim of full TX closure.
  d72 = bytes(stock72) if stock72 is not None else None
  d96 = pack_lat96(phase, direction, mag_norm, profiles)
  return d72, d96


def score_in_sample(samples: list[Sample], profiles: dict[int, PhaseProfile]) -> dict:
  total = 0
  exact = 0
  per_byte = [0] * 9
  by_phase = defaultdict(lambda: {"n": 0, "exact": 0})
  for s in samples:
    pred = pack_lat96(s.phase, s.label, 1.0, profiles)
    if pred is None:
      continue
    total += 1
    by_phase[s.phase]["n"] += 1
    if pred == s.d96:
      exact += 1
      by_phase[s.phase]["exact"] += 1
    for i, (a, b) in enumerate(zip(pred, s.d96)):
      if a == b:
        per_byte[i] += 1
  return {
    "scored": total,
    "exact_match_rate": round(exact / total, 4) if total else 0.0,
    "per_byte_match": {f"b{i}": round(v / total, 4) if total else 0.0 for i, v in enumerate(per_byte)},
    "per_phase": {p: {"n": v["n"], "exact_rate": round(v["exact"] / v["n"], 4) if v["n"] else 0.0} for p, v in sorted(by_phase.items())},
  }


def main() -> int:
  ap = argparse.ArgumentParser(description="Build BMW i3 lateral 72/96 shadow payloads")
  ap.add_argument("--phase", type=int, help="72/96 phase byte")
  ap.add_argument("--direction", choices=("left", "right"), help="lateral direction")
  ap.add_argument("--mag-norm", type=float, default=1.0, help="normalized magnitude 0..1")
  ap.add_argument("--stock72", help="optional stock 72 payload hex for pass-through")
  args = ap.parse_args()

  samples = collect_labeled_samples()
  profiles = build_phase_profiles(samples)

  if args.phase is not None and args.direction is not None:
    stock72 = bytes.fromhex(args.stock72) if args.stock72 else None
    d72, d96 = pack_shadow_lat(args.phase, args.direction, args.mag_norm, stock72, profiles)
    profile = profiles.get(args.phase)
    print({
      "phase": args.phase,
      "direction": args.direction,
      "mag_norm": round(max(0.0, min(1.0, float(args.mag_norm))), 4),
      "magnitude_confidence": profile.magnitude_confidence if profile else "none",
      "payload72": d72.hex() if d72 is not None else None,
      "payload96": d96.hex() if d96 is not None else None,
    })
    return 0

  print("profiles")
  for phase in sorted(profiles):
    print(vars(profiles[phase]))

  print("\nscore")
  print(score_in_sample(samples, profiles))

  print("\nexamples")
  for phase in sorted(profiles):
    for direction in ("left", "right"):
      for mag_norm in (0.0, 0.5, 1.0):
        payload = pack_lat96(phase, direction, mag_norm, profiles)
        if payload is not None:
          print({
            "phase": phase,
            "direction": direction,
            "mag_norm": mag_norm,
            "payload96": payload.hex(),
            "magnitude_confidence": profiles[phase].magnitude_confidence,
          })
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
