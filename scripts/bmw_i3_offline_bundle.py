#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path("/home/gericho/sunnypilot")
VENV_PY = ROOT / ".venv/bin/python"
REPLAY = ROOT / "scripts/bmw_i3_replay_report.py"
SHADOW = ROOT / "scripts/extract_bmw_i3_shadow_logs.py"


def main() -> int:
  route = sys.argv[1] if len(sys.argv) > 1 else None

  print("# BMW i3 Offline Bundle")
  print("\n## Shadow Logs")
  subprocess.run([str(VENV_PY), str(SHADOW)], check=False)

  print("\n## Replay Report")
  cmd = [str(VENV_PY), str(REPLAY)]
  if route is not None:
    cmd.append(route)
  subprocess.run(cmd, check=False)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
