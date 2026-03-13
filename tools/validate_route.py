#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_DATA_DIR = Path("/home/gericho/.comma/media/0/realdata")


def run_ffprobe(path: Path) -> tuple[dict, str]:
  cmd = [
    "ffprobe",
    "-v", "error",
    "-f", "hevc",
    "-count_frames",
    "-show_entries", "stream=nb_read_frames,r_frame_rate,avg_frame_rate",
    "-of", "json",
    str(path),
  ]
  proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
  if proc.returncode != 0:
    raise RuntimeError(proc.stderr.strip() or f"ffprobe failed for {path}")
  return json.loads(proc.stdout), proc.stderr


def count_drop_events(swaglog: Path) -> int:
  count = 0
  with swaglog.open("r", errors="ignore") as f:
    for line in f:
      if "roadEncodeData: dropping frame" in line:
        count += 1
  return count


def resolve_route(route_arg: str, data_dir: Path) -> tuple[str, list[Path]]:
  route_path = Path(route_arg)
  route_id = route_arg
  if route_path.exists():
    name = route_path.name
    route_id = name.rsplit("--", 1)[0]
  elif route_arg.endswith(("--0", "--1", "--2", "--3", "--4", "--5", "--6", "--7", "--8", "--9")):
    route_id = route_arg.rsplit("--", 1)[0]

  segments = sorted(data_dir.glob(f"{route_id}--*"))
  if not segments:
    raise FileNotFoundError(f"route not found: {route_id}")
  return route_id, segments


def validate_segment(segment: Path, expected_fps: int, expected_length: int, allow_partial: bool) -> list[str]:
  issues: list[str] = []
  for name in ("fcamera.hevc", "qlog.zst", "rlog.zst"):
    if not (segment / name).exists():
      issues.append(f"missing {name}")

  fcamera = segment / "fcamera.hevc"
  if not fcamera.exists():
    return issues

  probe, stderr = run_ffprobe(fcamera)
  streams = probe.get("streams", [])
  if not streams:
    issues.append("ffprobe returned no streams")
    return issues

  stream = streams[0]
  frame_count = int(stream.get("nb_read_frames", "0"))
  r_frame_rate = stream.get("r_frame_rate", "unknown")
  avg_frame_rate = stream.get("avg_frame_rate", "unknown")

  expected_frames = expected_fps * expected_length - 1
  min_frames = int(expected_frames * 0.95)
  if allow_partial:
    min_frames = 1

  if frame_count < min_frames:
    issues.append(f"frame_count={frame_count} expected>={min_frames}")
  if r_frame_rate != f"{expected_fps}/1":
    issues.append(f"r_frame_rate={r_frame_rate} expected={expected_fps}/1")
  if "Could not find ref with POC" in stderr:
    issues.append("hevc decode references broken")
  if avg_frame_rate != f"{expected_fps}/1":
    issues.append(f"avg_frame_rate={avg_frame_rate} (informational on raw HEVC)")
  return issues


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate a locally recorded route")
  parser.add_argument("route", help="route id or segment path, e.g. 0000004c--9df7b29f35")
  parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
  parser.add_argument("--expected-fps", type=int, default=int(os.getenv("ROAD_FPS", "10")))
  parser.add_argument("--expected-segment-length", type=int, default=60)
  parser.add_argument("--swaglog", default="", help="path to swaglog, or 'latest'")
  args = parser.parse_args()

  data_dir = Path(args.data_dir)
  route_id, segments = resolve_route(args.route, data_dir)

  print(f"route={route_id}")
  print(f"segments={len(segments)}")

  bad = False
  for i, segment in enumerate(segments):
    allow_partial = i == len(segments) - 1
    issues = validate_segment(segment, args.expected_fps, args.expected_segment_length, allow_partial)
    status = "ok" if not [x for x in issues if "avg_frame_rate=" not in x] else "fail"
    print(f"{segment.name}: {status}")
    for issue in issues:
      print(f"  - {issue}")
    if status != "ok":
      bad = True

  if args.swaglog:
    swaglog = Path(args.swaglog)
    if args.swaglog == "latest":
      logs = sorted(Path("/home/gericho/.comma/log").glob("swaglog.*"))
      swaglog = logs[-1] if logs else Path()
    if swaglog.exists():
      drops = count_drop_events(swaglog)
      print(f"swaglog={swaglog}")
      print(f"road_drops={drops}")
      bad = bad or drops > 0
    else:
      print(f"swaglog_missing={swaglog}")
      bad = True

  return 1 if bad else 0


if __name__ == "__main__":
  sys.exit(main())
