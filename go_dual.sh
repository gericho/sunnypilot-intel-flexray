#!/usr/bin/env bash
set -e

cd ~/sunnypilot
source .venv/bin/activate

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

OPENCL_ICD_DIR="/tmp/opencl-intel-icd"
mkdir -p "${OPENCL_ICD_DIR}"
cp /etc/OpenCL/vendors/intel.icd "${OPENCL_ICD_DIR}/intel.icd"
export OCL_ICD_VENDORS="${OPENCL_ICD_DIR}"

export_default RUN_PROFILE full_experimental
export_default DISABLE_BOOTLOG 1
export_default DISABLE_QCAMERA 1
export DEV=CL
export_default HEVC_VAAPI_ASYNC_DEPTH 4
export_default HEVC_ENCODER vaapi
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
  full_experimental)
    export_default DISABLE_MODELD 0
    export_default LOG_ONLY_MODE 0
    ;;
  log_modeld)
    export_default DISABLE_MODELD 0
    export_default LOG_ONLY_MODE 1
    ;;
  log_only_stable)
    export_default DISABLE_MODELD 0
    export_default LOG_ONLY_MODE 1
    ;;
  can_soc_scan)
    export_default DISABLE_MODELD 1
    export_default DISABLE_ENCODERD 0
    export_default LOG_ONLY_MODE 1
    ;;
  *)
    echo "Unknown RUN_PROFILE: ${RUN_PROFILE}" >&2
    exit 1
    ;;
esac

export_default WEBCAM_FLIP -1
export_default USE_WEBCAM 1
export_default DUAL_CAMERA 0
export_default NOSENSOR 1
export_default PYTHONUNBUFFERED 1
export PYTHONPATH="$PWD"
export SDL_VIDEO_WINDOW_POS="${UI_X},${UI_Y}"
export WINDOW_POS="${UI_X},${UI_Y}"

export_default WEBCAM_PROFILE 0
export_default WEBCAM_PROFILE_INTERVAL 5
export_default WEBCAM_BACKEND ffmpeg
export_default WEBCAM_MJPG_QSV 1
export_default WEBCAM_BRIO_FOV 65
# PC rig intrinsics: keep road/wide configurable from the launcher without patching modeld/UI.
export_default ROAD_HFOV_DEG 60
export_default WIDE_HFOV_DEG 58.1
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
export_default ORT_OPENVINO_PERFORMANCE_HINT THROUGHPUT
export_default ORT_OPENVINO_EXECUTION_MODE PERFORMANCE
export_default ORT_OPENVINO_NUM_STREAMS 2
export_default ORT_OPENVINO_CACHE_DIR "$PWD/.cache/openvino_model_cache"

export_default ENABLE_BMW_I3_SHADOW_LOGGER 1
export_default BMW_I3_SHADOW_LOGGER_INTERVAL 0.2
export_default BMW_I3_SHADOW_LOGGER_OUT /tmp/bmw_i3_shadow/rlog.jsonl
export_default BMW_I3_SHADOW_LOGGER_ERR /tmp/bmw_i3_shadow_logger.stderr
export_default BMW_I3_SHADOW_LOGGER_PID /tmp/bmw_i3_shadow_logger.pid

if [ "${DISABLE_QCAMERA}" = "1" ]; then
  touch /tmp/disable_qcamera
else
  rm -f /tmp/disable_qcamera
fi

export_default ROAD_CAM 0
export_default ROAD_W 640
export_default ROAD_H 360
export_default ROAD_FPS 20
export_default ROAD_FOURCC MJPG

export_default DRIVER_W 640
export_default DRIVER_H 480
export_default DRIVER_FPS 20
export_default DRIVER_FOURCC YUYV

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

if [ "${ENABLE_BMW_I3_SHADOW_LOGGER}" = "1" ]; then
  pkill -f "scripts/bmw_i3_shadow_logger.py" >/dev/null 2>&1 || true
  rm -f "${BMW_I3_SHADOW_LOGGER_PID}"
  mkdir -p "$(dirname "${BMW_I3_SHADOW_LOGGER_OUT}")"
  nohup python "$PWD/scripts/bmw_i3_shadow_logger.py"     --out "${BMW_I3_SHADOW_LOGGER_OUT}"     --interval "${BMW_I3_SHADOW_LOGGER_INTERVAL}"     >>"${BMW_I3_SHADOW_LOGGER_ERR}" 2>&1 &
  echo $! > "${BMW_I3_SHADOW_LOGGER_PID}"
fi

cd system/manager
exec ./manager.py
