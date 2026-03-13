#!/usr/bin/env bash
set -e

cd ~/sunnypilot
source .venv/bin/activate

export SP_DEVICE_TYPE=PC
export BIG=1 # set comma3X layout instead of comma4
export SCALE=0.4
#export NO_DM=1 # disable driver camera check

# Force OpenCL to Intel iGPU ICD only.
# tinygrad CL runtime picks the first platform, so excluding POCL/rusticl
# prevents accidental CPU OpenCL fallback.
OPENCL_ICD_DIR="/tmp/opencl-intel-icd"
mkdir -p "${OPENCL_ICD_DIR}"
cp /etc/OpenCL/vendors/intel.icd "${OPENCL_ICD_DIR}/intel.icd"
export OCL_ICD_VENDORS="${OPENCL_ICD_DIR}"

# Options: 0 = enabled, 1 = disabled
export DISABLE_MODELD=1
export DISABLE_BOOTLOG=1
export DISABLE_QCAMERA=1
# Log-only profile (recommended for route capture on PC):
# blocks driving stack processes that are not needed for CAN+video logging.
export LOG_ONLY_MODE=1
export DEV=CL
export HEVC_VAAPI_ASYNC_DEPTH=4
export HEVC_ENCODER=vaapi
# Use software H264 for qcamera (QSV probe on this host falls back anyway).
# Accepted values: auto | vaapi | qsv | cpu
export QCAMERA_ENCODER=cpu
export VAAPI_DEVICE=/dev/dri/renderD128
export ROAD_MAIN_BITRATE_LOW=2500000
export ROAD_MAIN_BITRATE_HIGH=3500000
export LOGGERD_ENCODER_QUEUE_LIMIT=1200
export QCAM_BITRATE=120000
export QCAM_FPS=5
export WEBCAM_RAW_NV12=1
# NOTE: on this host/driver HEVC_VAAPI_LOW_POWER=1 fails with
# "No usable encoding entrypoint found for profile VAProfileHEVCMain".
#
# Webcam flip mode:
# -1 = flip both axes (180 deg)
#  0 = vertical flip
#  1 = horizontal flip
#  none = no flip
export WEBCAM_FLIP=none

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

# Mirror qcamera toggle into a runtime flag file so native daemons can read it reliably.
if [ "${DISABLE_QCAMERA}" = "1" ]; then
  touch /tmp/disable_qcamera
else
  rm -f /tmp/disable_qcamera
fi

# Camera indexes (if the code uses indexes)
export ROAD_CAM=0
# Buses to use for car fingerprinting (legacy CAN + FlexRay gateway buses).
export FINGERPRINT_BUSES=0,1,13,23,24
#export DRIVER_CAM=4

# Road camera parameters
export ROAD_W=1280
export ROAD_H=720
export ROAD_FPS=10
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

if [ "$LOG_ONLY_MODE" = "1" ]; then
  LOG_ONLY_BLOCKS="selfdrived,controlsd,plannerd,radard,card,dmonitoringd,dmonitoringmodeld,locationd,calibrationd,torqued,paramsd,lagd,soundd,mapd,mapd_manager,models_manager"
  if [ -n "$BLOCK_LIST" ]; then
    BLOCK_LIST="$BLOCK_LIST,$LOG_ONLY_BLOCKS"
  else
    BLOCK_LIST="$LOG_ONLY_BLOCKS"
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
