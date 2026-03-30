#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from statistics import mean
import sys

sys.path.insert(0, "/home/gericho/sunnypilot")
from tools.lib.logreader import LogReader


ROOT = Path("/home/gericho/.comma/media/0/realdata")


def route_mtime(route_dir: Path) -> dt.datetime:
  return dt.datetime.fromtimestamp((route_dir / "rlog.zst").stat().st_mtime)


def routes_for_day(day: str) -> list[Path]:
  out = []
  for d in sorted(ROOT.iterdir()):
    rlog = d / "rlog.zst"
    if not rlog.exists():
      continue
    if route_mtime(d).strftime("%Y-%m-%d") == day:
      out.append(d)
  return out


def analyze_route(route_dir: str) -> dict:
  d = Path(route_dir)
  rlog = d / "rlog.zst"
  c72 = Counter()
  c96 = Counter()
  frames = 0
  can_events = 0
  for evt in LogReader(str(rlog), only_union_types=True):
    if evt.which() != "can":
      continue
    can_events += 1
    for m in evt.can:
      frames += 1
      if (m.src, m.address) == (0, 72):
        c72[bytes(m.dat).hex()] += 1
      elif (m.src, m.address) == (0, 96):
        c96[bytes(m.dat).hex()] += 1

  return {
    "route": d.name,
    "ts": route_mtime(d).strftime("%Y-%m-%d %H:%M:%S CET"),
    "can_events": can_events,
    "frames": frames,
    "n72": sum(c72.values()),
    "u72": len(c72),
    "n96": sum(c96.values()),
    "u96": len(c96),
    "top72": c72.most_common(6),
    "top96": c96.most_common(6),
    "set72": sorted(c72.keys()),
    "set96": sorted(c96.keys()),
  }


def jaccard(a: set[str], b: set[str]) -> float:
  if not a and not b:
    return 1.0
  return len(a & b) / len(a | b)


def heat_bucket(value: float) -> str:
  if value >= 0.85:
    return "██"
  if value >= 0.70:
    return "▓▓"
  if value >= 0.50:
    return "▒▒"
  if value >= 0.30:
    return "░░"
  return ".."


def enrich(rows: list[dict]) -> list[dict]:
  by_name = {r["route"]: r for r in rows}
  for r in rows:
    s72 = set(r["set72"])
    s96 = set(r["set96"])
    sims72 = []
    sims96 = []
    other72 = set()
    other96 = set()
    for o in rows:
      if o["route"] == r["route"]:
        continue
      os72 = set(o["set72"])
      os96 = set(o["set96"])
      sims72.append(jaccard(s72, os72))
      sims96.append(jaccard(s96, os96))
      other72 |= os72
      other96 |= os96
    r["sim72_mean"] = mean(sims72) if sims72 else 1.0
    r["sim96_mean"] = mean(sims96) if sims96 else 1.0
    r["uniq72"] = [(h, c) for h, c in r["top72"] if h not in other72][:3]
    r["uniq96"] = [(h, c) for h, c in r["top96"] if h not in other96][:3]
    r["dist_score"] = round(
      (1.0 - r["sim72_mean"]) * 100.0 +
      (1.0 - r["sim96_mean"]) * 100.0 +
      r["u72"] * 0.5 +
      r["u96"] * 0.2,
      3,
    )
  rows.sort(key=lambda r: r["dist_score"], reverse=True)
  return rows


def print_summary(rows: list[dict], top_n: int) -> None:
  print("# RAW only heatmap for fr0_72 / fr0_96")
  print("# route timestamp n72/u72 n96/u96 sim72 sim96 score heat72 heat96")
  for r in rows[:top_n]:
    print(
      f"{r['route']} {r['ts']} "
      f"{r['n72']}/{r['u72']} {r['n96']}/{r['u96']} "
      f"{r['sim72_mean']:.3f} {r['sim96_mean']:.3f} {r['dist_score']:.3f} "
      f"{heat_bucket(1.0 - r['sim72_mean'])} {heat_bucket(1.0 - r['sim96_mean'])}"
    )
    if r["uniq72"]:
      print(f"  uniq72: {r['uniq72']}")
    if r["uniq96"]:
      print(f"  uniq96: {r['uniq96']}")
    print(f"  top72: {r['top72'][:3]}")
    print(f"  top96: {r['top96'][:3]}")


def write_csv(rows: list[dict], path: Path) -> None:
  with path.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
      "route", "timestamp", "n72", "u72", "n96", "u96",
      "sim72_mean", "sim96_mean", "dist_score",
      "top72_1", "top72_1_count", "top72_2", "top72_2_count", "top72_3", "top72_3_count",
      "top96_1", "top96_1_count", "top96_2", "top96_2_count", "top96_3", "top96_3_count",
    ])
    for r in rows:
      top72 = r["top72"] + [("", 0)] * 3
      top96 = r["top96"] + [("", 0)] * 3
      w.writerow([
        r["route"], r["ts"], r["n72"], r["u72"], r["n96"], r["u96"],
        f"{r['sim72_mean']:.6f}", f"{r['sim96_mean']:.6f}", f"{r['dist_score']:.3f}",
        top72[0][0], top72[0][1], top72[1][0], top72[1][1], top72[2][0], top72[2][1],
        top96[0][0], top96[0][1], top96[1][0], top96[1][1], top96[2][0], top96[2][1],
      ])


def main() -> int:
  ap = argparse.ArgumentParser(description="BMW i3 raw 72/96 per-route heatmap")
  ap.add_argument("--day", default="2026-03-24")
  ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 4) // 2)))
  ap.add_argument("--top", type=int, default=15)
  ap.add_argument("--out-json", default="/home/gericho/sunnypilot/tmp/bmw_i3_raw_lat_heatmap.json")
  ap.add_argument("--out-csv", default="/home/gericho/sunnypilot/tmp/bmw_i3_raw_lat_heatmap.csv")
  args = ap.parse_args()

  route_dirs = routes_for_day(args.day)
  if not route_dirs:
    raise SystemExit(f"no routes found for {args.day}")

  rows: list[dict] = []
  with ProcessPoolExecutor(max_workers=args.jobs) as ex:
    futs = {ex.submit(analyze_route, str(d)): d for d in route_dirs}
    for fut in as_completed(futs):
      rows.append(fut.result())

  rows = enrich(rows)

  out_json = Path(args.out_json)
  out_json.parent.mkdir(parents=True, exist_ok=True)
  out_json.write_text(json.dumps(rows, indent=2))
  write_csv(rows, Path(args.out_csv))
  print_summary(rows, args.top)
  print(f"# wrote_json {out_json}")
  print(f"# wrote_csv {args.out_csv}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
