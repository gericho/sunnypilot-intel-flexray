#!/usr/bin/env bash
set -e

cd ~/sunnypilot
source .venv/bin/activate

unset BLOCK
unset LOG_ONLY_MODE
unset WEBCAM_DIRECT_SPLIT
unset UI_FORCE_WIDE_MAIN
unset WEBCAM_MAIN_IS_WIDE
unset ROAD_CAM
unset WIDE_CAM

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
export_default QCAMERA_ENCODER auto
export_default VAAPI_DEVICE /dev/dri/renderD128
export_default ROAD_MAIN_BITRATE_LOW 2500000
export_default ROAD_MAIN_BITRATE_HIGH 3500000
export_default LOGGERD_ENCODER_QUEUE_LIMIT 1200
export_default QCAM_BITRATE 120000
export_default QCAM_FPS 5
export_default WEBCAM_RAW_NV12 1
export_default DISABLE_ENCODERD 0
export_default DISABLE_LOGGERD 0

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
    export_default DISABLE_ENCODERD 1
    export_default LOG_ONLY_MODE 1
    ;;
  *)
    echo "Unknown RUN_PROFILE: ${RUN_PROFILE}" >&2
    exit 1
    ;;
esac

export_default WEBCAM_FLIP off
export_default USE_WEBCAM 1
export_default DUAL_CAMERA 0
export_default NOSENSOR 1
export_default PYTHONUNBUFFERED 1
export PYTHONPATH="$PWD"
export SDL_VIDEO_WINDOW_POS="${UI_X},${UI_Y}"
export WINDOW_POS="${UI_X},${UI_Y}"

export_default WEBCAM_PROFILE 0
export_default WEBCAM_PROFILE_INTERVAL 5
export_default WEBCAM_BRIO_FOV 90
export WEBCAM_SPLIT_ENABLE=1
export WEBCAM_DIRECT_SPLIT=1
export WEBCAM_SPLIT_SOURCE_CAM=0
export WEBCAM_SPLIT_WIDE_CAM=10
export WEBCAM_SPLIT_ROAD_CAM=11
export ROAD_CAM=11
export WIDE_CAM=10
export WEBCAM_BACKEND=ffmpeg
export WEBCAM_ROAD_BACKEND=ffmpeg
export WEBCAM_WIDE_BACKEND=ffmpeg
export WEBCAM_FFMPEG_OUTPUT=bgr24
export WEBCAM_ROAD_FFMPEG_OUTPUT=nv12
export WEBCAM_WIDE_FFMPEG_OUTPUT=nv12
export WEBCAM_MJPG_QSV=0
export WEBCAM_MAIN_IS_WIDE=0
export UI_FORCE_WIDE_MAIN=0
export ROAD_W=640
export ROAD_H=360
export WIDE_W=640
export WIDE_H=360
export WIDE_FPS=20
export WIDE_FOURCC=NV12
export ROAD_FPS=20
export ROAD_FOURCC=NV12
# PC rig intrinsics: keep road/wide configurable from the launcher without patching modeld/UI.
export_default ROAD_HFOV_DEG 40
export_default WIDE_HFOV_DEG 82.1
export_default ROAD_FOCAL_PIXELS 879.1927742254792
export_default WIDE_FOCAL_PIXELS 367.46973980632804
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
export ORT_OPENVINO_DEVICE=GPU
export_default ORT_OPENVINO_FALLBACK_CPU 0
export_default ORT_OPENVINO_DISABLE_ORT_OPT 1
export_default ORT_OPENVINO_PERFORMANCE_HINT LATENCY
export_default ORT_OPENVINO_EXECUTION_MODE PERFORMANCE
export_default ORT_OPENVINO_NUM_STREAMS 2
export_default ORT_INTRA_OP_THREADS 2
export_default MODEL_PREPARE_ONLY_THRESHOLD 1
export MODEL_POSE_DIAG=1
export MODEL_WARP_DIAG=1
export MODEL_RAW_BUF_DIAG=1
export_default ORT_OPENVINO_CACHE_DIR "$PWD/.cache/openvino_model_cache"

export_default ENABLE_BMW_I3_SHADOW_LOGGER 1
export_default DISABLE_WIDE_RECORDING 0
export_default BMW_I3_SHADOW_LOGGER_INTERVAL 0.2
export_default BMW_I3_SHADOW_LOGGER_OUT /tmp/bmw_i3_shadow/rlog.jsonl
export_default BMW_I3_SHADOW_LOGGER_ERR /tmp/bmw_i3_shadow_logger.stderr
export_default BMW_I3_SHADOW_LOGGER_PID /tmp/bmw_i3_shadow_logger.pid

if [ "${WEBCAM_SPLIT_ENABLE}" = "1" ] && [ "${WEBCAM_DIRECT_SPLIT:-0}" != "1" ]; then
  src_dev="/dev/video${WEBCAM_SPLIT_SOURCE_CAM}"
  wide_dev="/dev/video${WEBCAM_SPLIT_WIDE_CAM}"
  road_dev="/dev/video${WEBCAM_SPLIT_ROAD_CAM}"
  if [ ! -e "$src_dev" ] || [ ! -e "$wide_dev" ] || [ ! -e "$road_dev" ]; then
    echo "Missing webcam split devices: $src_dev $wide_dev $road_dev" >&2
    exit 1
  fi
  pkill -f "ffmpeg.*${wide_dev}.*${road_dev}" >/dev/null 2>&1 || true
  v4l2-ctl -d "$src_dev" --set-ctrl=auto_exposure=1 >/dev/null 2>&1 || true
  v4l2-ctl -d "$src_dev" --set-ctrl=exposure_time_absolute=${WEBCAM_MANUAL_EXPOSURE} >/dev/null 2>&1 || true
  v4l2-ctl -d "$src_dev" --set-ctrl=gain=${WEBCAM_MANUAL_GAIN} >/dev/null 2>&1 || true
  v4l2-ctl -d "$src_dev" --set-ctrl=backlight_compensation=0 >/dev/null 2>&1 || true
  v4l2-ctl -d "$src_dev" --set-ctrl=focus_automatic_continuous=0 >/dev/null 2>&1 || true
  python - <<'PYCAM'
import os
from openpilot.tools.webcam.camera import _set_brio_fov
_set_brio_fov(f"/dev/video{os.getenv('WEBCAM_SPLIT_SOURCE_CAM','0')}", os.getenv('WEBCAM_BRIO_FOV','90'))
PYCAM
  {
    echo "PWD=$PWD"
    echo "BASH=$(command -v bash)"
    echo "FFMPEG=$(command -v ffmpeg)"
    ls -l ./tools/webcam/split_dual.sh
  } >/tmp/webcam_splitter_trace.log 2>&1
  : >/tmp/webcam_splitter.log
  ./tools/webcam/split_dual.sh "$src_dev" "$wide_dev" "$road_dev" "${WIDE_FPS}" >/tmp/webcam_splitter.log 2>&1 &
  export WEBCAM_SPLITTER_PID=$!
  sleep 2
  if ! kill -0 "$WEBCAM_SPLITTER_PID" >/dev/null 2>&1; then
    echo "webcam splitter exited early" >&2
    sed -n '1,40p' /tmp/webcam_splitter_trace.log >&2 || true
    sed -n '1,80p' /tmp/webcam_splitter.log >&2 || true
    exit 1
  fi
  (
    while kill -0 "$WEBCAM_SPLITTER_PID" >/dev/null 2>&1; do
      sleep 1
    done
    echo "webcam splitter died; stopping runtime" >&2
    pkill -f 'manager.py|controlsd|modeld_tinygrad|webcamerad|encoderd|loggerd|camerad|ffmpeg .*video10|ffmpeg .*video11|split_dual.sh' >/dev/null 2>&1 || true
  ) >/tmp/webcam_splitter_watch.log 2>&1 &
fi

if [ "${DISABLE_QCAMERA}" = "1" ]; then
  touch /tmp/disable_qcamera
else
  rm -f /tmp/disable_qcamera
fi

export_default DRIVER_W 640
export_default DRIVER_H 480
export_default DRIVER_FPS 20
export_default DRIVER_FOURCC YUYV

BLOCK_LIST=""

if [ "$DISABLE_MODELD" = "1" ]; then
  append_block "modeld,modeld_tinygrad"
fi

if [ "$DISABLE_BOOTLOG" = "1" ]; then
  append_block "bootlog"
fi

if [ "$DISABLE_ENCODERD" = "1" ]; then
  append_block "encoderd"
fi

if [ "$DISABLE_LOGGERD" = "1" ]; then
  append_block "loggerd,uploader,deleter"
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
