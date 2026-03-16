#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def resolve_log_path() -> Path:
  if len(sys.argv) > 1:
    return Path(sys.argv[1]).expanduser()

  log_dir = Path("/home/gericho/.comma/log")
  candidates = sorted(log_dir.glob("swaglog.*"), key=lambda p: p.stat().st_mtime, reverse=True)
  if not candidates:
    raise FileNotFoundError("no swaglog files found in /home/gericho/.comma/log")
  return candidates[0]


def main() -> int:
  log_path = resolve_log_path()
  print(f"LOG={log_path}")

  wanted = ("bmw_i3_shadow_acc", "bmw_i3_shadow_long")
  count = 0
  with log_path.open("r", encoding="utf-8", errors="replace") as f:
    for line in f:
      if any(tag in line for tag in wanted):
        print(line.rstrip())
        count += 1

  if count == 0:
    print("no BMW i3 shadow debug lines found")
  else:
    print(f"matched_lines={count}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
