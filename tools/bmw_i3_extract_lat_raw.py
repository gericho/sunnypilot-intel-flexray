#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, "/home/gericho/sunnypilot/opendbc_repo")
from opendbc.car.logreader import LogReader


TJA_GATE_131 = 640
TJA_STATE_135 = 24802
TJA_TAIL_135 = "2228e2604206"
LATERAL_IDS = (72, 96, 131, 135)


def resolve_segments(route: str | Path, filename: str = "rlog.zst") -> list[Path]:
  p = Path(route)
  if p.name == filename:
    return [p]
  stem = p.name.rsplit("--", 1)[0] + "--"
  return [seg / filename for seg in sorted(p.parent.glob(f"{stem}*")) if (seg / filename).exists()]


def u16le(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


def extract(route: str, start_sec: float | None, end_sec: float | None, tja_only: bool) -> list[dict]:
  rows: list[dict] = []
  seg_base = 0.0
  for rlog in resolve_segments(route):
    first_ts = None
    max_rel = 0.0
    last: dict[int, bytes | None] = {72: None, 96: None, 131: None, 135: None}
    for evt in LogReader(str(rlog), only_union_types=True):
      if evt.which() != "can":
        continue
      ts = evt.logMonoTime / 1e9
      if first_ts is None:
        first_ts = ts
      rel = ts - first_ts
      max_rel = rel
      touched = False
      for m in evt.can:
        dat = bytes(m.dat)
        if (m.src, m.address) in ((0, 72), (0, 96), (0, 131), (0, 135)) and len(dat) >= 9:
          last[m.address] = dat
          touched = True
      if not touched or not all(last.values()):
        continue
      t_sec = seg_base + rel
      if start_sec is not None and t_sec < start_sec:
        continue
      if end_sec is not None and t_sec > end_sec:
        continue

      gate131 = u16le(last[131], 5)  # type: ignore[arg-type]
      state135 = u16le(last[135], 5)  # type: ignore[arg-type]
      tail135 = last[135][3:9].hex()  # type: ignore[index]
      is_tja = gate131 == TJA_GATE_131 and state135 == TJA_STATE_135 and tail135 == TJA_TAIL_135
      if tja_only and not is_tja:
        continue

      d72 = last[72]  # type: ignore[assignment]
      d96 = last[96]  # type: ignore[assignment]
      d131 = last[131]  # type: ignore[assignment]
      d135 = last[135]  # type: ignore[assignment]
      rows.append({
        "t_sec": round(t_sec, 3),
        "phase72": d72[0],
        "frame72_hex": d72[:9].hex(),
        "frame96_hex": d96[:9].hex(),
        "frame131_hex": d131[:9].hex(),
        "frame135_hex": d135[:9].hex(),
        "b1_96": d96[1],
        "b2_96": d96[2],
        "b3_96": d96[3],
        "gate131": gate131,
        "state135": state135,
        "tail135": tail135,
        "tja_state": is_tja,
      })
    seg_base += max_rel
  return rows


def write_json(path: Path, rows: list[dict]) -> None:
  path.write_text(json.dumps(rows, indent=2))


def write_csv(path: Path, rows: list[dict]) -> None:
  with path.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [
      "t_sec", "phase72", "frame72_hex", "frame96_hex", "frame131_hex", "frame135_hex",
      "b1_96", "b2_96", "b3_96", "gate131", "state135", "tail135", "tja_state",
    ])
    w.writeheader()
    w.writerows(rows)


def main() -> int:
  ap = argparse.ArgumentParser(description="Extract BMW i3 lateral raw frames from rlog into JSON/CSV.")
  ap.add_argument("route", help="Route segment path, e.g. .../00000402--59a94efa08--0")
  ap.add_argument("--start-sec", type=float, default=None)
  ap.add_argument("--end-sec", type=float, default=None)
  ap.add_argument("--tja-only", action="store_true", help="Keep only clean TJA window samples")
  ap.add_argument("--json-out", type=Path, default=Path("/home/gericho/sunnypilot/tmp/bmw_i3_lat_raw.json"))
  ap.add_argument("--csv-out", type=Path, default=Path("/home/gericho/sunnypilot/tmp/bmw_i3_lat_raw.csv"))
  ap.add_argument("--print-limit", type=int, default=20)
  args = ap.parse_args()

  rows = extract(args.route, args.start_sec, args.end_sec, args.tja_only)
  write_json(args.json_out, rows)
  write_csv(args.csv_out, rows)

  print(f"route={args.route}")
  print(f"rows={len(rows)}")
  print(f"json_out={args.json_out}")
  print(f"csv_out={args.csv_out}")
  for row in rows[:args.print_limit]:
    print(
      f"t={row['t_sec']:.3f} "
      f"72=({row['frame72_hex']}) "
      f"96=({row['frame96_hex']}) "
      f"131=({row['frame131_hex']}) "
      f"135=({row['frame135_hex']})"
    )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
