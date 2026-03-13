#!/usr/bin/env bash
set -e

cd ~/sunnypilot
source .venv/bin/activate

export_default() {
  local name="$1"
  local value="$2"
  if [ -z "${!name+x}" ]; then
    export "${name}=${value}"
  fi
}

append_block() {
  local value="$1"
  if [ -n "$BLOCK_LIST" ]; then
    BLOCK_LIST="$BLOCK_LIST,$value"
  else
    BLOCK_LIST="$value"
  fi
}

export_default SP_DEVICE_TYPE PC
export_default BIG 1
export_default SCALE 0.4
#export NO_DM=1 # disable driver camera check

# Force OpenCL to Intel iGPU ICD only.
# tinygrad CL runtime picks the first platform, so excluding POCL/rusticl
# prevents accidental CPU OpenCL fallback.
OPENCL_ICD_DIR="/tmp/opencl-intel-icd"
mkdir -p "${OPENCL_ICD_DIR}"
cp /etc/OpenCL/vendors/intel.icd "${OPENCL_ICD_DIR}/intel.icd"
export OCL_ICD_VENDORS="${OPENCL_ICD_DIR}"

# Runtime profiles:
# - log_only_stable: fcamera-only logging tuned for reliable Cabana playback on PC
# - log_modeld: keeps modeld enabled while preserving the stable logging defaults
# - full_experimental: minimal blocking for broader bring-up/debug sessions
export_default RUN_PROFILE log_only_stable

export_default DISABLE_BOOTLOG 1
export_default DISABLE_QCAMERA 1
export_default DEV CL
export_default HEVC_VAAPI_ASYNC_DEPTH 4
export_default HEVC_ENCODER vaapi
# Accepted values: auto | vaapi | qsv | cpu
export_default QCAMERA_ENCODER cpu
export_default VAAPI_DEVICE /dev/dri/renderD128
export_default ROAD_MAIN_BITRATE_LOW 2500000
export_default ROAD_MAIN_BITRATE_HIGH 3500000
export_default LOGGERD_ENCODER_QUEUE_LIMIT 1200
export_default QCAM_BITRATE 120000
export_default QCAM_FPS 5
export_default WEBCAM_RAW_NV12 1

case "${RUN_PROFILE}" in
  log_only_stable)
    export_default DISABLE_MODELD 1
    export_default LOG_ONLY_MODE 1
    ;;
  log_modeld)
    export_default DISABLE_MODELD 0
    export_default LOG_ONLY_MODE 1
    ;;
  full_experimental)
    export_default DISABLE_MODELD 0
    export_default LOG_ONLY_MODE 0
    ;;
  *)
    echo "Unknown RUN_PROFILE: ${RUN_PROFILE}" >&2
    exit 1
    ;;
esac

# NOTE: on this host/driver HEVC_VAAPI_LOW_POWER=1 fails with
# "No usable encoding entrypoint found for profile VAProfileHEVCMain".
#
# Webcam flip mode:
# -1 = flip both axes (180 deg)
#  0 = vertical flip
#  1 = horizontal flip
#  none = no flip
export_default WEBCAM_FLIP none

# PC/webcam mode
export_default FORCE_ONROAD 1
#export REPLAY=1
#export SIMULATOR=1

# Only for testing without panda, put all to 1
#export NO_PANDA=1
#export IGNORE_PANDA=1
#export PASSIVE=1

export_default USE_WEBCAM 1
export_default DUAL_CAMERA 0
export_default NOSENSOR 1
export_default PYTHONUNBUFFERED 1
export PYTHONPATH="$PWD"
export_default WEBCAM_PROFILE 1
export_default WEBCAM_PROFILE_INTERVAL 5

# Mirror qcamera toggle into a runtime flag file so native daemons can read it reliably.
if [ "${DISABLE_QCAMERA}" = "1" ]; then
  touch /tmp/disable_qcamera
else
  rm -f /tmp/disable_qcamera
fi

# Camera indexes (if the code uses indexes)
export_default ROAD_CAM 0
# Buses to use for car fingerprinting (legacy CAN + FlexRay gateway buses).
export_default FINGERPRINT_BUSES 0,1,13,23,24
#export DRIVER_CAM=4

# Road camera parameters
export_default ROAD_W 1280
export_default ROAD_H 720
export_default ROAD_FPS 10
export_default ROAD_FOURCC NV12 # YUYV NV12 MJPG

# Driver camera parameters
export_default DRIVER_W 640
export_default DRIVER_H 480
export_default DRIVER_FPS 20
export_default DRIVER_FOURCC YUYV # YUYV NV12 MJPG

# Build BLOCK list
BLOCK_LIST=""

if [ "$DISABLE_MODELD" = "1" ]; then
  append_block "modeld"
fi

if [ "$DISABLE_BOOTLOG" = "1" ]; then
  append_block "bootlog"
fi

if [ "$LOG_ONLY_MODE" = "1" ]; then
  LOG_ONLY_BLOCKS="selfdrived,controlsd,plannerd,radard,card,dmonitoringd,dmonitoringmodeld,locationd,calibrationd,torqued,paramsd,lagd,soundd,mapd,mapd_manager,models_manager"
  append_block "$LOG_ONLY_BLOCKS"
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
