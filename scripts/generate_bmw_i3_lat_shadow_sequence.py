#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from tools.lib.logreader import LogReader

from build_bmw_i3_lat_shadow_packer import (
  PHASE_THRESHOLDS,
  build_phase_profiles,
  collect_labeled_samples,
  pack_shadow_lat,
)


def expand_route_segments(route: str) -> list[Path]:
  p = Path(route)
  if p.is_file():
    if p.name == "rlog.zst":
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
  out = [seg / "rlog.zst" for seg in segs if (seg / "rlog.zst").exists()]
  if not out:
    if (p / "rlog.zst").exists():
      return [p / "rlog.zst"]
    raise FileNotFoundError(f"no route segments found for {route}")
  return out


def infer_direction_and_mag(phase: int, b1: int, profiles) -> tuple[str | None, float, str]:
  profile = profiles.get(phase)
  if profile is None:
    return None, 0.0, "none"
  direction = "right" if b1 > profile.threshold else "left"
  ladder = profile.ladder_right if direction == "right" else profile.ladder_left
  if ladder:
    ordered = [triple[0] for triple in ladder]
    nearest_idx = min(range(len(ordered)), key=lambda i: abs(ordered[i] - b1))
    mag = nearest_idx / max(1, len(ordered) - 1)
    return direction, mag, profile.magnitude_confidence

  if direction == "right":
    span = max(1.0, float(profile.b1_right) - profile.threshold)
    mag = (float(b1) - profile.threshold) / span
  else:
    span = max(1.0, profile.threshold - float(profile.b1_left))
    mag = (profile.threshold - float(b1)) / span
  return direction, max(0.0, min(1.0, mag)), profile.magnitude_confidence


def main() -> int:
  ap = argparse.ArgumentParser(description="Generate BMW i3 72/96 shadow sequence from a stock route")
  ap.add_argument("route", help="route dir, segment dir, or rlog.zst")
  ap.add_argument("--jsonl-out", help="optional output file for per-sample rows")
  args = ap.parse_args()

  profiles = build_phase_profiles(collect_labeled_samples())
  rows = []
  last72 = None
  start = None

  for rlog in expand_route_segments(args.route):
    for evt in LogReader(str(rlog)):
      if start is None:
        start = evt.logMonoTime
      t = (evt.logMonoTime - start) / 1e9
      if evt.which() != "can":
        continue
      for c in evt.can:
        dat = bytes(c.dat)
        if c.src == 0 and c.address == 72 and len(dat) >= 9:
          last72 = (t, dat)
        elif c.src == 0 and c.address == 96 and len(dat) >= 9 and last72 is not None:
          if abs(last72[0] - t) > 0.03:
            continue
          d72 = last72[1]
          phase = d72[0]
          if phase != dat[0] or phase not in PHASE_THRESHOLDS:
            continue
          direction, mag_norm, mag_conf = infer_direction_and_mag(phase, dat[1], profiles)
          if direction is None:
            continue
          shadow72, shadow96 = pack_shadow_lat(phase, direction, mag_norm, d72, profiles)
          rows.append({
            "t": round(t, 3),
            "phase": phase,
            "direction": direction,
            "mag_norm": round(mag_norm, 4),
            "mag_confidence": mag_conf,
            "stock72": d72.hex(),
            "stock96": dat.hex(),
            "shadow72": shadow72.hex() if shadow72 is not None else None,
            "shadow96": shadow96.hex() if shadow96 is not None else None,
            "exact96": shadow96 == dat if shadow96 is not None else False,
          })

  if args.jsonl_out:
    out = Path(args.jsonl_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
      for row in rows:
        f.write(json.dumps(row) + "\n")

  exact = sum(1 for r in rows if r["exact96"])
  by_phase = Counter(r["phase"] for r in rows)
  exact_by_phase = Counter(r["phase"] for r in rows if r["exact96"])
  print({
    "rows": len(rows),
    "exact96_rate": round(exact / len(rows), 4) if rows else 0.0,
    "by_phase": dict(sorted(by_phase.items())),
    "exact_by_phase": {p: {"n": by_phase[p], "exact_rate": round(exact_by_phase[p] / by_phase[p], 4)} for p in sorted(by_phase)},
    "jsonl_out": args.jsonl_out,
  })
  for row in rows[:20]:
    print(row)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
