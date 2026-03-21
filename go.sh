#!/usr/bin/env bash
set -e

cd ~/sunnypilot
source .venv/bin/activate

# Reset stale runtime profile state from previous shells/runs.
unset BLOCK
unset LOG_ONLY_MODE
unset DISABLE_MODELD

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
export_default NO_DM 1
export_default UI_X 1488
export_default UI_Y 0

# Force OpenCL to Intel iGPU ICD only.
# tinygrad CL runtime picks the first platform, so excluding POCL/rusticl
# prevents accidental CPU OpenCL fallback.
OPENCL_ICD_DIR="/tmp/opencl-intel-icd"
mkdir -p "${OPENCL_ICD_DIR}"
cp /etc/OpenCL/vendors/intel.icd "${OPENCL_ICD_DIR}/intel.icd"
export OCL_ICD_VENDORS="${OPENCL_ICD_DIR}"

# Runtime profiles:
# - can_soc_scan: logger-only capture for CAN/SOC hunting with encoderd on and modeld off
# - log_only_stable: fcamera-only logging tuned for reliable Cabana playback on PC
# - log_modeld: keeps modeld enabled while preserving the stable logging defaults
# - full_experimental: minimal blocking for broader bring-up/debug sessions
#
# Default to the onroad bring-up profile for this host. Override RUN_PROFILE
# explicitly when you want logger-only capture or other runtime mixes.
export_default RUN_PROFILE full_experimental

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
export_default WEBCAM_RAW_NV12 0
export_default DISABLE_ENCODERD 0

case "${RUN_PROFILE}" in
  can_soc_scan)
    export_default DISABLE_MODELD 1
    export_default DISABLE_ENCODERD 0
    export_default LOG_ONLY_MODE 1
    ;;
  log_only_stable)
    export_default DISABLE_MODELD 0
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
export_default WEBCAM_FLIP -1

# PC/webcam mode
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
export_default UBLOX_TTY /dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_7_-_GPS_GNSS_Receiver-if00
export PYTHONPATH="$PWD"
export SDL_VIDEO_WINDOW_POS="${UI_X},${UI_Y}"
export WINDOW_POS="${UI_X},${UI_Y}"
export_default WEBCAM_PROFILE 0
export_default WEBCAM_PROFILE_INTERVAL 5
export_default WEBCAM_BACKEND ffmpeg
export_default WEBCAM_BRIO_FOV 65
export_default WEBCAM_MAIN_IS_WIDE 1
# Logitech BRIO FoV presets are diagonal. Convert the selected preset to the
# horizontal 16:9 FoV used by our PC intrinsics/model config.
BRIO_HFOV_DEG="$(python - <<'PY'
import math
diag_fov = 65.0
w, h = 16.0, 9.0
diag = math.hypot(w, h)
hfov = 2.0 * math.degrees(math.atan(math.tan(math.radians(diag_fov / 2.0)) * (w / diag)))
print(f"{hfov:.6f}")
PY
)"
export_default ROAD_HFOV_DEG "${BRIO_HFOV_DEG}"
export_default WIDE_HFOV_DEG "${BRIO_HFOV_DEG}"
export_default WEBCAM_DYNAMIC_EXPOSURE 1
export_default WEBCAM_DYNAMIC_GAIN 0
export_default WEBCAM_MANUAL_EXPOSURE 24
export_default WEBCAM_MANUAL_GAIN 0
export_default WEBCAM_DYNAMIC_EXPOSURE_MIN 8
export_default WEBCAM_DYNAMIC_EXPOSURE_MAX 500
export_default WEBCAM_DYNAMIC_EXPOSURE_INITIAL 250
export_default WEBCAM_DYNAMIC_EXPOSURE_INTERVAL 0.5
export_default WEBCAM_DYNAMIC_EXPOSURE_SAMPLE_EVERY 10
export_default WEBCAM_DYNAMIC_EXPOSURE_TARGET_LOW 70
export_default WEBCAM_DYNAMIC_EXPOSURE_TARGET_HIGH 135
export_default WEBCAM_DYNAMIC_EXPOSURE_TARGET_MID 96
export_default WEBCAM_DYNAMIC_EXPOSURE_MAX_DELTA 80
export_default WEBCAM_DYNAMIC_GAIN_MAX 255
export_default WEBCAM_DYNAMIC_GAIN_START_EXPOSURE 120
export_default WEBCAM_DYNAMIC_GAIN_FULL_EXPOSURE 1500
export_default FORCE_MODEL_RUNNER tinygrad
export_default USE_ONNX 1
export_default ORT_BACKEND openvino
export_default ORT_OPENVINO_DEVICE GPU
export_default ORT_OPENVINO_FALLBACK_CPU 1
export_default ORT_OPENVINO_DISABLE_ORT_OPT 1
export_default ORT_OPENVINO_PERFORMANCE_HINT LATENCY
export_default ORT_OPENVINO_EXECUTION_MODE PERFORMANCE
export_default ORT_OPENVINO_NUM_STREAMS 1
export_default ORT_OPENVINO_CACHE_DIR "$PWD/.cache/openvino_model_cache"
export_default ENABLE_BMW_I3_SHADOW_LOGGER 1
export_default BMW_I3_SHADOW_LOGGER_INTERVAL 0.2
export_default BMW_I3_SHADOW_LOGGER_OUT /tmp/bmw_i3_shadow/rlog.jsonl
export_default BMW_I3_SHADOW_LOGGER_ERR /tmp/bmw_i3_shadow_logger.stderr
export_default BMW_I3_SHADOW_LOGGER_PID /tmp/bmw_i3_shadow_logger.pid

# Mirror qcamera toggle into a runtime flag file so native daemons can read it reliably.
if [ "${DISABLE_QCAMERA}" = "1" ]; then
  touch /tmp/disable_qcamera
else
  rm -f /tmp/disable_qcamera
fi

# Camera indexes (if the code uses indexes)
export_default ROAD_CAM 0
export_default FINGERPRINT BMW_I3_EXPERIMENTAL
# Buses to use for car fingerprinting (legacy CAN + FlexRay gateway buses).
export_default FINGERPRINT_BUSES 0,1,13,23,24
#export DRIVER_CAM=4

# Road camera parameters
export_default ROAD_W 640
export_default ROAD_H 360
export_default ROAD_FPS 20
export_default ROAD_FOURCC MJPG # YUYV NV12 MJPG
export_default PC_CALIB_FREEZE 0

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

if [ "$DISABLE_ENCODERD" = "1" ]; then
  append_block "encoderd"
fi

if [ "${NO_DM}" = "1" ]; then
  append_block "dmonitoringd,dmonitoringmodeld"
fi

if [ "$LOG_ONLY_MODE" = "1" ]; then
  LOG_ONLY_BLOCKS="selfdrived,controlsd,plannerd,radard,card,dmonitoringd,dmonitoringmodeld,locationd,calibrationd,torqued,paramsd,lagd,soundd,mapd,mapd_manager,models_manager"
  append_block "$LOG_ONLY_BLOCKS"
fi

if [ -n "$BLOCK_LIST" ]; then
  export BLOCK="$BLOCK_LIST"
fi

if [ -n "${DRIVER_CAM:-}" ] && [ -e "/dev/video${DRIVER_CAM}" ]; then
  v4l2-ctl -d "/dev/video${DRIVER_CAM}" --set-fmt-video=width=${DRIVER_W},height=${DRIVER_H},pixelformat=${DRIVER_FOURCC} || true
  v4l2-ctl -d "/dev/video${DRIVER_CAM}" --set-parm=${DRIVER_FPS} || true
fi

if [ "${PC_CALIB_FREEZE}" = "1" ]; then
  python - <<'PY'
import os
import cereal.messaging as messaging
from openpilot.common.params import Params

pitch = float(os.getenv("PC_CALIB_PITCH_RAD", "0.059738"))
yaw = float(os.getenv("PC_CALIB_YAW_RAD", "0.03705092892050743"))

msg = messaging.new_message('liveCalibration')
msg.liveCalibration.validBlocks = 20
msg.liveCalibration.rpyCalib = [0.0, pitch, yaw]
Params().put("CalibrationParams", msg.to_bytes())
PY
fi

if [ "${ENABLE_BMW_I3_SHADOW_LOGGER}" = "1" ]; then
  pkill -f "scripts/bmw_i3_shadow_logger.py" >/dev/null 2>&1 || true
  rm -f "${BMW_I3_SHADOW_LOGGER_PID}"
  nohup python "$PWD/scripts/bmw_i3_shadow_logger.py" \
    --out "${BMW_I3_SHADOW_LOGGER_OUT}" \
    --interval "${BMW_I3_SHADOW_LOGGER_INTERVAL}" \
    >>"${BMW_I3_SHADOW_LOGGER_ERR}" 2>&1 &
  echo $! > "${BMW_I3_SHADOW_LOGGER_PID}"
fi

cd system/manager
./manager.py
