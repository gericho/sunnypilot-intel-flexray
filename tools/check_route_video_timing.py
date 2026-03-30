#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path

from opendbc.car.logreader import LogReader


def ffprobe_json(path: Path, *args: str) -> dict:
  cmd = ["ffprobe", "-v", "error", *args, "-of", "json", str(path)]
  return json.loads(subprocess.check_output(cmd, text=True))


def video_stats(path: Path) -> dict:
  stream_info = ffprobe_json(path, "-select_streams", "v:0", "-show_streams")
  packet_info = ffprobe_json(path, "-select_streams", "v:0", "-show_packets")
  stream = stream_info["streams"][0]
  packets = packet_info.get("packets", [])
  packet_count = len(packets)
  packet_duration = float(packets[0]["duration_time"]) if packets and "duration_time" in packets[0] else None
  real_duration = (packet_count * packet_duration) if packet_count and packet_duration else None
  return {
    "path": str(path),
    "codec": stream.get("codec_name"),
    "r_frame_rate": stream.get("r_frame_rate"),
    "avg_frame_rate": stream.get("avg_frame_rate"),
    "time_base": stream.get("time_base"),
    "packet_count": packet_count,
    "packet_duration_s": packet_duration,
    "real_duration_s": real_duration,
  }


def log_duration(path: Path) -> float | None:
  first = None
  last = None
  for msg in LogReader(str(path)):
    t = msg.logMonoTime / 1e9
    if first is None:
      first = t
    last = t
  if first is None or last is None:
    return None
  return last - first


def main() -> None:
  parser = argparse.ArgumentParser(description="Check route video fps metadata against packet cadence and log duration.")
  parser.add_argument("route_dir", help="Path to segment directory containing ecamera.hevc/fcamera.hevc/rlog.zst")
  args = parser.parse_args()

  route_dir = Path(args.route_dir)
  for name in ("ecamera.hevc", "fcamera.hevc"):
    path = route_dir / name
    if path.exists():
      stats = video_stats(path)
      print(f"{name}:")
      print(f"  codec={stats['codec']}")
      print(f"  r_frame_rate={stats['r_frame_rate']}")
      print(f"  avg_frame_rate={stats['avg_frame_rate']}")
      print(f"  time_base={stats['time_base']}")
      print(f"  packet_count={stats['packet_count']}")
      print(f"  packet_duration_s={stats['packet_duration_s']}")
      print(f"  real_duration_s={stats['real_duration_s']:.3f}" if stats["real_duration_s"] is not None else "  real_duration_s=N/A")

  for name in ("rlog.zst", "qlog.zst"):
    path = route_dir / name
    if path.exists():
      dur = log_duration(path)
      print(f"{name}:")
      print(f"  duration_s={dur:.3f}" if dur is not None else "  duration_s=N/A")


if __name__ == "__main__":
  main()
