#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path


def resolve_default_csv() -> Path:
  return Path("/home/gericho/sunnypilot/captures/bmw_i3_long_shadow_sequence.csv")


def main() -> int:
  ap = argparse.ArgumentParser(description="Replay a BMW i3 long shadow sequence without transmitting anything")
  ap.add_argument("csv_path", nargs="?", help="path to bmw_i3_long_shadow_sequence.csv")
  ap.add_argument("--speed", type=float, default=1.0, help="replay speed multiplier; 0 disables sleeping")
  ap.add_argument("--limit", type=int, default=0, help="optional max number of rows to replay")
  args = ap.parse_args()

  csv_path = Path(args.csv_path) if args.csv_path else resolve_default_csv()
  if not csv_path.exists():
    raise FileNotFoundError(csv_path)

  with csv_path.open("r", encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))

  if args.limit > 0:
    rows = rows[:args.limit]

  print(f"# replaying {csv_path}")
  print("# sec mode branch phase target_parity target_wb target_wc")

  prev_sec = None
  start = time.monotonic()
  for row in rows:
    sec = int(row["sec"])
    if args.speed > 0 and prev_sec is not None:
      dt = (sec - prev_sec) / args.speed
      if dt > 0:
        time.sleep(dt)
    print(
      f"{sec:4d} {row['mode']:10s} {row['branch']:4s} {row['phase']:>4s} "
      f"{row['target_parity']:>4s} {row['target_wb']:>8s} {row['target_wc']:>8s}",
      flush=True,
    )
    prev_sec = sec

  elapsed = time.monotonic() - start
  print(f"# done rows={len(rows)} elapsed_s={elapsed:.3f} speed={args.speed}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
