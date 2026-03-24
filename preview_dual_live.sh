#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

cleanup() {
  pkill -f 'ffplay .*video10|ffplay .*video11|ffmpeg .*video10|ffmpeg .*video11|split_dual.sh' >/dev/null 2>&1 || true
}

cleanup

if [ ! -e /dev/video0 ]; then
  echo 'missing /dev/video0'
  exit 1
fi

if [ ! -e /dev/video10 ] || [ ! -e /dev/video11 ]; then
  echo 'missing /dev/video10 or /dev/video11'
  echo 'run: sudo ./tools/webcam/setup_loopback.sh'
  exit 1
fi

./tools/webcam/split_dual.sh /dev/video0 /dev/video10 /dev/video11 20 >/tmp/manual_splitter.log 2>&1 &
SPLITTER_PID=$!
sleep 2

if ! kill -0 "$SPLITTER_PID" >/dev/null 2>&1; then
  echo 'splitter exited early'
  cat /tmp/manual_splitter.log || true
  exit 1
fi

/usr/bin/ffplay -f v4l2 -input_format nv12 -video_size 640x360 /dev/video10 >/tmp/ffplay_video10.log 2>&1 &
FFPLAY_WIDE_PID=$!
sleep 1
/usr/bin/ffplay -f v4l2 -input_format nv12 -video_size 512x256 /dev/video11 >/tmp/ffplay_video11.log 2>&1 &
FFPLAY_ROAD_PID=$!

wait "$FFPLAY_WIDE_PID" "$FFPLAY_ROAD_PID" || true
cleanup
