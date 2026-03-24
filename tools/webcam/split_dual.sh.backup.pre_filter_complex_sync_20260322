#!/usr/bin/env bash
set -euo pipefail

src_dev="${1:?missing source device}"
wide_dev="${2:?missing wide device}"
road_dev="${3:?missing road device}"
wide_fps="${4:?missing wide fps}"
ffmpeg_bin="${FFMPEG_BIN:-/usr/bin/ffmpeg}"

exec "${ffmpeg_bin}" -hide_banner -loglevel error   -f v4l2 -pixel_format mjpeg -framerate "${wide_fps}" -video_size 1280x720 -i "${src_dev}"   -map 0:v -vf 'scale=640:360,format=nv12' -pix_fmt nv12 -f v4l2 "${wide_dev}"   -map 0:v -vf 'crop=840:420:220:150,scale=512:256,format=nv12' -pix_fmt nv12 -f v4l2 "${road_dev}"
