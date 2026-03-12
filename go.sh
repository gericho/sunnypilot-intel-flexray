#!/usr/bin/env bash
set -e

cd ~/sunnypilot
source .venv/bin/activate

export SP_DEVICE_TYPE=PC
export BIG=1 # set comma3X layout instead of comma4
export SCALE=0.4
#export NO_DM=1 # disable driver camera check

# Options: 0 = enabled, 1 = disabled
export DISABLE_MODELD=0
export DISABLE_BOOTLOG=1
export DEV=CL
export HEVC_VAAPI_ASYNC_DEPTH=4
# NOTE: on this host/driver HEVC_VAAPI_LOW_POWER=1 fails with
# "No usable encoding entrypoint found for profile VAProfileHEVCMain".
#
# Webcam flip mode:
# -1 = flip both axes (180 deg)
#  0 = vertical flip
#  1 = horizontal flip
#  none = no flip
export WEBCAM_FLIP=-1

# PC/webcam mode
export FORCE_ONROAD=1
#export REPLAY=1
#export SIMULATOR=1

# Only for testing without panda, put all to 1
#export NO_PANDA=1
#export IGNORE_PANDA=1
#export PASSIVE=1

export USE_WEBCAM=1
export DUAL_CAMERA=0
export NOSENSOR=1
export PYTHONUNBUFFERED=1
export PYTHONPATH="$PWD"
export WEBCAM_PROFILE=1
export WEBCAM_PROFILE_INTERVAL=5

# Camera indexes (if the code uses indexes)
export ROAD_CAM=0
#export DRIVER_CAM=4

# Road camera parameters
export ROAD_W=1280
export ROAD_H=720
export ROAD_FPS=20
export ROAD_FOURCC=NV12 # YUYV NV12 MJPG

# Driver camera parameters
export DRIVER_W=640
export DRIVER_H=480
export DRIVER_FPS=20
export DRIVER_FOURCC=YUYV # YUYV NV12 MJPG

# Build BLOCK list
BLOCK_LIST=""

if [ "$DISABLE_MODELD" = "1" ]; then
  BLOCK_LIST="modeld"
fi

if [ "$DISABLE_BOOTLOG" = "1" ]; then
  if [ -n "$BLOCK_LIST" ]; then
    BLOCK_LIST="$BLOCK_LIST,bootlog"
  else
    BLOCK_LIST="bootlog"
  fi
fi

if [ -n "$BLOCK_LIST" ]; then
  export BLOCK="$BLOCK_LIST"
fi

# Configure V4L2 hardware settings (best effort)
v4l2-ctl -d /dev/video0 --set-fmt-video=width=${ROAD_W},height=${ROAD_H},pixelformat=${ROAD_FOURCC} || true
v4l2-ctl -d /dev/video0 --set-parm=${ROAD_FPS} || true

# Disable autofocus (Logitech BRIO only)
v4l2-ctl -d /dev/video0 --set-ctrl=focus_automatic_continuous=0 || true

if [ -n "${DRIVER_CAM:-}" ] && [ -e "/dev/video${DRIVER_CAM}" ]; then
  v4l2-ctl -d "/dev/video${DRIVER_CAM}" --set-fmt-video=width=${DRIVER_W},height=${DRIVER_H},pixelformat=${DRIVER_FOURCC} || true
  v4l2-ctl -d "/dev/video${DRIVER_CAM}" --set-parm=${DRIVER_FPS} || true
fi

cd system/manager
./manager.py
