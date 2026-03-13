#include "system/loggerd/encoder/ffmpeg_encoder.h"

#include <fcntl.h>
#include <unistd.h>

#include <cassert>
#include <cstring>
#include <cstdio>
#include <cstdlib>

#define __STDC_CONSTANT_MACROS

#include "third_party/libyuv/include/libyuv.h"

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/hwcontext.h>
#include <libavutil/imgutils.h>
#include <libavutil/opt.h>
}

#include "common/swaglog.h"
#include "common/util.h"

const int env_debug_encoder = (getenv("DEBUG_ENCODER") != NULL) ? atoi(getenv("DEBUG_ENCODER")) : 0;

FfmpegEncoder::FfmpegEncoder(const EncoderInfo &encoder_info, int in_width, int in_height)
    : VideoEncoder(encoder_info, in_width, in_height) {
  frame = av_frame_alloc();
  assert(frame);
  frame->format = AV_PIX_FMT_YUV420P;
  frame->width = out_width;
  frame->height = out_height;
  frame->linesize[0] = out_width;
  frame->linesize[1] = out_width/2;
  frame->linesize[2] = out_width/2;

  convert_buf.resize(in_width * in_height * 3 / 2);

  if (in_width != out_width || in_height != out_height) {
    downscale_buf.resize(out_width * out_height * 3 / 2);
  }
}

FfmpegEncoder::~FfmpegEncoder() {
  encoder_close();
  av_frame_free(&frame);
  av_frame_free(&sw_frame);
  av_frame_free(&hw_frame);
  av_buffer_unref(&hw_frames_ctx);
  av_buffer_unref(&hw_device_ctx);
}

bool FfmpegEncoder::init_vaapi(const char *device_path) {
  int err = av_hwdevice_ctx_create(&hw_device_ctx, AV_HWDEVICE_TYPE_VAAPI, device_path, nullptr, 0);
  if (err < 0) {
    LOGW("av_hwdevice_ctx_create failed for %s (%d)", device_path, err);
    return false;
  }

  hw_frames_ctx = av_hwframe_ctx_alloc(hw_device_ctx);
  if (hw_frames_ctx == nullptr) {
    LOGW("av_hwframe_ctx_alloc failed");
    return false;
  }

  auto *frames_ctx = reinterpret_cast<AVHWFramesContext *>(hw_frames_ctx->data);
  frames_ctx->format = AV_PIX_FMT_VAAPI;
  frames_ctx->sw_format = AV_PIX_FMT_NV12;
  frames_ctx->width = out_width;
  frames_ctx->height = out_height;
  frames_ctx->initial_pool_size = 8;

  err = av_hwframe_ctx_init(hw_frames_ctx);
  if (err < 0) {
    LOGW("av_hwframe_ctx_init failed (%d)", err);
    return false;
  }
  return true;
}

void FfmpegEncoder::encoder_open() {
  const auto settings = encoder_info.get_settings(in_width);
  const bool qcamera_h264 = settings.encode_type == cereal::EncodeIndex::Type::QCAMERA_H264;
  const char *device = getenv("VAAPI_DEVICE");
  if (device == nullptr || device[0] == '\0') device = "/dev/dri/renderD128";

  use_vaapi = false;
  use_qsv = false;
  const AVCodec *codec = nullptr;

  auto is_auto = [](const char *v) { return v == nullptr || strcmp(v, "auto") == 0; };
  auto is_set = [](const char *v, const char *name) { return v != nullptr && strcmp(v, name) == 0; };

  if (qcamera_h264) {
    const char *qcam_impl = getenv("QCAMERA_ENCODER");
    const bool try_vaapi = is_auto(qcam_impl) || is_set(qcam_impl, "vaapi");
    const bool try_qsv = is_auto(qcam_impl) || is_set(qcam_impl, "qsv");
    if (try_vaapi) {
      codec = avcodec_find_encoder_by_name("h264_vaapi");
      if (codec != nullptr) {
        use_vaapi = init_vaapi(device);
      }
    }
    if ((!use_vaapi || codec == nullptr) && try_qsv) {
      codec = avcodec_find_encoder_by_name("h264_qsv");
      if (codec != nullptr) use_qsv = true;
    }
    if (codec == nullptr || (!use_vaapi && !use_qsv)) {
      codec = avcodec_find_encoder(AV_CODEC_ID_H264);
      use_vaapi = false;
      use_qsv = false;
      LOGW("fallback to software H264 encoder for qcamera");
    }
  } else {
    const char *hevc_impl = getenv("HEVC_ENCODER");
    const bool try_vaapi = is_auto(hevc_impl) || is_set(hevc_impl, "vaapi");
    const bool try_qsv = is_auto(hevc_impl) || is_set(hevc_impl, "qsv");
    if (try_vaapi) {
      codec = avcodec_find_encoder_by_name("hevc_vaapi");
      if (codec != nullptr) {
        use_vaapi = init_vaapi(device);
      }
    }
    if ((!use_vaapi || codec == nullptr) && try_qsv) {
      codec = avcodec_find_encoder_by_name("hevc_qsv");
      if (codec != nullptr) use_qsv = true;
    }
    if (codec == nullptr || (!use_vaapi && !use_qsv)) {
      codec = avcodec_find_encoder(AV_CODEC_ID_HEVC);
      use_vaapi = false;
      use_qsv = false;
      LOGW("fallback to software HEVC encoder");
    }
  }
  if (codec == nullptr) {
    LOGE("no encoder found for %s", encoder_info.publish_name);
    return;
  }

  this->codec_ctx = avcodec_alloc_context3(codec);
  if (this->codec_ctx == nullptr) {
    LOGE("avcodec_alloc_context3 failed for %s", encoder_info.publish_name);
    return;
  }
  this->codec_ctx->width = frame->width;
  this->codec_ctx->height = frame->height;
  this->codec_ctx->pix_fmt = use_vaapi ? AV_PIX_FMT_VAAPI : (use_qsv ? AV_PIX_FMT_NV12 : AV_PIX_FMT_YUV420P);
  this->codec_ctx->time_base = (AVRational){ 1, encoder_info.fps };
  this->codec_ctx->framerate = (AVRational){ encoder_info.fps, 1 };
  this->codec_ctx->bit_rate = settings.bitrate;
  this->codec_ctx->gop_size = settings.gop_size;
  this->codec_ctx->max_b_frames = 0;

  if (!qcamera_h264 && !use_vaapi && codec_ctx->priv_data != nullptr) {
    // Keep HEVC deterministic and low-latency for real-time logging on PC.
    av_opt_set(codec_ctx->priv_data, "preset", "ultrafast", 0);
    av_opt_set(codec_ctx->priv_data, "tune", "zerolatency", 0);
    av_opt_set(codec_ctx->priv_data, "x265-params", "bframes=0:repeat-headers=1", 0);
  }
  if (use_vaapi) {
    LOGW("using VAAPI encoder %s for %s", codec->name, encoder_info.publish_name);
    codec_ctx->hw_device_ctx = av_buffer_ref(hw_device_ctx);
    codec_ctx->hw_frames_ctx = av_buffer_ref(hw_frames_ctx);
    sw_frame = av_frame_alloc();
    hw_frame = av_frame_alloc();
    if (sw_frame == nullptr || hw_frame == nullptr) {
      LOGW("failed to allocate VAAPI frames, fallback to software encoder");
      av_frame_free(&sw_frame);
      av_frame_free(&hw_frame);
      avcodec_free_context(&codec_ctx);
      use_vaapi = false;
      codec = qcamera_h264 ? avcodec_find_encoder(AV_CODEC_ID_H264) : avcodec_find_encoder(AV_CODEC_ID_HEVC);
      if (codec == nullptr) {
        LOGE("software fallback encoder not found for %s", encoder_info.publish_name);
        return;
      }
      this->codec_ctx = avcodec_alloc_context3(codec);
      if (this->codec_ctx == nullptr) {
        LOGE("avcodec_alloc_context3 failed for software fallback %s", encoder_info.publish_name);
        return;
      }
      this->codec_ctx->width = frame->width;
      this->codec_ctx->height = frame->height;
      this->codec_ctx->pix_fmt = AV_PIX_FMT_YUV420P;
      this->codec_ctx->time_base = (AVRational){ 1, encoder_info.fps };
      this->codec_ctx->framerate = (AVRational){ encoder_info.fps, 1 };
      this->codec_ctx->bit_rate = settings.bitrate;
      this->codec_ctx->gop_size = settings.gop_size;
      this->codec_ctx->max_b_frames = 0;
      if (!qcamera_h264 && codec_ctx->priv_data != nullptr) {
        av_opt_set(codec_ctx->priv_data, "preset", "ultrafast", 0);
        av_opt_set(codec_ctx->priv_data, "tune", "zerolatency", 0);
        av_opt_set(codec_ctx->priv_data, "x265-params", "bframes=0:repeat-headers=1", 0);
      }
    } else {
      sw_frame->format = AV_PIX_FMT_NV12;
      sw_frame->width = out_width;
      sw_frame->height = out_height;
      int berr = av_frame_get_buffer(sw_frame, 32);
      if (berr < 0) {
        LOGW("av_frame_get_buffer failed (%d), fallback to software encoder", berr);
        av_frame_free(&sw_frame);
        av_frame_free(&hw_frame);
        avcodec_free_context(&codec_ctx);
        use_vaapi = false;
        codec = qcamera_h264 ? avcodec_find_encoder(AV_CODEC_ID_H264) : avcodec_find_encoder(AV_CODEC_ID_HEVC);
        if (codec == nullptr) {
          LOGE("software fallback encoder not found for %s", encoder_info.publish_name);
          return;
        }
        this->codec_ctx = avcodec_alloc_context3(codec);
        if (this->codec_ctx == nullptr) {
          LOGE("avcodec_alloc_context3 failed for software fallback %s", encoder_info.publish_name);
          return;
        }
        this->codec_ctx->width = frame->width;
        this->codec_ctx->height = frame->height;
        this->codec_ctx->pix_fmt = AV_PIX_FMT_YUV420P;
        this->codec_ctx->time_base = (AVRational){ 1, encoder_info.fps };
        this->codec_ctx->framerate = (AVRational){ encoder_info.fps, 1 };
        this->codec_ctx->bit_rate = settings.bitrate;
        this->codec_ctx->gop_size = settings.gop_size;
        this->codec_ctx->max_b_frames = 0;
        if (!qcamera_h264 && codec_ctx->priv_data != nullptr) {
          av_opt_set(codec_ctx->priv_data, "preset", "ultrafast", 0);
          av_opt_set(codec_ctx->priv_data, "tune", "zerolatency", 0);
          av_opt_set(codec_ctx->priv_data, "x265-params", "bframes=0:repeat-headers=1", 0);
        }
      } else {
        nv12_buf.resize(out_width * out_height * 3 / 2);
      }
    }
  } else if (use_qsv) {
    LOGW("using QSV encoder %s for %s", codec->name, encoder_info.publish_name);
    if (codec_ctx->priv_data != nullptr) {
      // Keep real-time behavior deterministic on low-power CPUs.
      av_opt_set(codec_ctx->priv_data, "low_power", "0", 0);
      av_opt_set(codec_ctx->priv_data, "look_ahead", "0", 0);
      av_opt_set(codec_ctx->priv_data, "async_depth", "1", 0);
    }
    frame->format = AV_PIX_FMT_NV12;
    frame->linesize[0] = out_width;
    frame->linesize[1] = out_width;
    frame->linesize[2] = 0;
    nv12_buf.resize(out_width * out_height * 3 / 2);
  }

  int err = avcodec_open2(this->codec_ctx, codec, NULL);
  if (err < 0 && (use_vaapi || use_qsv)) {
    LOGW("hardware encoder open failed (%d), fallback to software for %s", err, encoder_info.publish_name);
    avcodec_free_context(&codec_ctx);
    av_frame_free(&sw_frame);
    av_frame_free(&hw_frame);
    use_vaapi = false;
    use_qsv = false;
    const AVCodec *sw_codec = qcamera_h264 ? avcodec_find_encoder(AV_CODEC_ID_H264) : avcodec_find_encoder(AV_CODEC_ID_HEVC);
    if (sw_codec == nullptr) {
      LOGE("software encoder unavailable for fallback %s", encoder_info.publish_name);
      return;
    }
    this->codec_ctx = avcodec_alloc_context3(sw_codec);
    if (this->codec_ctx == nullptr) {
      LOGE("avcodec_alloc_context3 failed for software fallback %s", encoder_info.publish_name);
      return;
    }
    this->codec_ctx->width = frame->width;
    this->codec_ctx->height = frame->height;
    this->codec_ctx->pix_fmt = AV_PIX_FMT_YUV420P;
    this->codec_ctx->time_base = (AVRational){ 1, encoder_info.fps };
    this->codec_ctx->framerate = (AVRational){ encoder_info.fps, 1 };
    this->codec_ctx->bit_rate = settings.bitrate;
    this->codec_ctx->gop_size = settings.gop_size;
    this->codec_ctx->max_b_frames = 0;
    if (!qcamera_h264 && codec_ctx->priv_data != nullptr) {
      av_opt_set(codec_ctx->priv_data, "preset", "ultrafast", 0);
      av_opt_set(codec_ctx->priv_data, "tune", "zerolatency", 0);
      av_opt_set(codec_ctx->priv_data, "x265-params", "bframes=0:repeat-headers=1", 0);
    }
    err = avcodec_open2(this->codec_ctx, sw_codec, NULL);
  }
  if (err < 0) {
    LOGE("avcodec_open2 failed (%d) for %s", err, encoder_info.publish_name);
    avcodec_free_context(&codec_ctx);
    return;
  }

  is_open = true;
  segment_num++;
  frame_counter = 0;
  packet_counter = 0;
}

void FfmpegEncoder::encoder_close() {
  if (!is_open) return;

  avcodec_free_context(&codec_ctx);
  av_frame_free(&sw_frame);
  av_frame_free(&hw_frame);
  is_open = false;
}

int FfmpegEncoder::encode_frame(VisionBuf* buf, VisionIpcBufExtra *extra) {
  assert(buf->width == this->in_width);
  assert(buf->height == this->in_height);

  const bool scaled = (in_width != out_width || in_height != out_height);
  if (use_vaapi) {
    uint8_t *dst_y = nv12_buf.data();
    uint8_t *dst_uv = dst_y + out_width * out_height;
    uint8_t *cy = convert_buf.data();
    uint8_t *cu = cy + in_width * in_height;
    uint8_t *cv = cu + (in_width / 2) * (in_height / 2);
    libyuv::NV12ToI420(buf->y, buf->stride,
                       buf->uv, buf->stride,
                       cy, in_width,
                       cu, in_width/2,
                       cv, in_width/2,
                       in_width, in_height);
    if (scaled) {
      uint8_t *sy = downscale_buf.data();
      uint8_t *su = sy + out_width * out_height;
      uint8_t *sv = su + (out_width / 2) * (out_height / 2);
      libyuv::I420Scale(cy, in_width,
                        cu, in_width/2,
                        cv, in_width/2,
                        in_width, in_height,
                        sy, out_width,
                        su, out_width/2,
                        sv, out_width/2,
                        out_width, out_height,
                        libyuv::kFilterBilinear);
      libyuv::I420ToNV12(sy, out_width, su, out_width/2, sv, out_width/2,
                         dst_y, out_width, dst_uv, out_width, out_width, out_height);
    } else {
      libyuv::I420ToNV12(cy, in_width, cu, in_width/2, cv, in_width/2,
                         dst_y, out_width, dst_uv, out_width, out_width, out_height);
    }

    int err = av_frame_make_writable(sw_frame);
    if (err < 0) {
      LOGE("av_frame_make_writable failed %d", err);
      return -1;
    }
    libyuv::CopyPlane(dst_y, out_width, sw_frame->data[0], sw_frame->linesize[0], out_width, out_height);
    libyuv::CopyPlane(dst_uv, out_width, sw_frame->data[1], sw_frame->linesize[1], out_width, out_height / 2);

    av_frame_unref(hw_frame);
    err = av_hwframe_get_buffer(codec_ctx->hw_frames_ctx, hw_frame, 0);
    if (err < 0) {
      LOGE("av_hwframe_get_buffer failed %d", err);
      return -1;
    }
    err = av_hwframe_transfer_data(hw_frame, sw_frame, 0);
    if (err < 0) {
      LOGE("av_hwframe_transfer_data failed %d", err);
      return -1;
    }
    hw_frame->pts = frame_counter++;

    int ret = 0;
    err = avcodec_send_frame(this->codec_ctx, hw_frame);
    if (err < 0) {
      LOGE("avcodec_send_frame error %d", err);
      return -1;
    }

    AVPacket pkt = {};
    pkt.data = NULL;
    pkt.size = 0;
    while (ret >= 0) {
      err = avcodec_receive_packet(this->codec_ctx, &pkt);
      if (err == AVERROR_EOF) {
        break;
      } else if (err == AVERROR(EAGAIN)) {
        ret = 0;
        break;
      } else if (err < 0) {
        LOGE("avcodec_receive_packet error %d", err);
        ret = -1;
        break;
      }

      publisher_publish(segment_num, packet_counter, *extra,
        (pkt.flags & AV_PKT_FLAG_KEY) ? V4L2_BUF_FLAG_KEYFRAME : 0,
        kj::arrayPtr<capnp::byte>(pkt.data, (size_t)0),
        kj::arrayPtr<capnp::byte>(pkt.data, pkt.size));
      packet_counter++;
      av_packet_unref(&pkt);
    }
    return ret;
  }

  if (use_qsv) {
    uint8_t *dst_y = nv12_buf.data();
    uint8_t *dst_uv = dst_y + out_width * out_height;
    if (scaled) {
      uint8_t *cy = convert_buf.data();
      uint8_t *cu = cy + in_width * in_height;
      uint8_t *cv = cu + (in_width / 2) * (in_height / 2);
      uint8_t *sy = downscale_buf.data();
      uint8_t *su = sy + out_width * out_height;
      uint8_t *sv = su + (out_width / 2) * (out_height / 2);
      libyuv::NV12ToI420(buf->y, buf->stride,
                         buf->uv, buf->stride,
                         cy, in_width,
                         cu, in_width/2,
                         cv, in_width/2,
                         in_width, in_height);
      libyuv::I420Scale(cy, in_width,
                        cu, in_width/2,
                        cv, in_width/2,
                        in_width, in_height,
                        sy, out_width,
                        su, out_width/2,
                        sv, out_width/2,
                        out_width, out_height,
                        libyuv::kFilterBilinear);
      libyuv::I420ToNV12(sy, out_width, su, out_width/2, sv, out_width/2,
                         dst_y, out_width, dst_uv, out_width, out_width, out_height);
    } else {
      libyuv::CopyPlane(buf->y, buf->stride, dst_y, out_width, out_width, out_height);
      libyuv::CopyPlane(buf->uv, buf->stride, dst_uv, out_width, out_width, out_height / 2);
    }
    frame->data[0] = dst_y;
    frame->data[1] = dst_uv;
    frame->data[2] = nullptr;
    frame->pts = frame_counter++;
    int ret = 0;

    int err = avcodec_send_frame(this->codec_ctx, frame);
    if (err < 0) {
      LOGE("avcodec_send_frame error %d", err);
      return -1;
    }

    AVPacket pkt = {};
    pkt.data = NULL;
    pkt.size = 0;
    while (ret >= 0) {
      err = avcodec_receive_packet(this->codec_ctx, &pkt);
      if (err == AVERROR_EOF) {
        break;
      } else if (err == AVERROR(EAGAIN)) {
        ret = 0;
        break;
      } else if (err < 0) {
        LOGE("avcodec_receive_packet error %d", err);
        ret = -1;
        break;
      }
      publisher_publish(segment_num, packet_counter, *extra,
        (pkt.flags & AV_PKT_FLAG_KEY) ? V4L2_BUF_FLAG_KEYFRAME : 0,
        kj::arrayPtr<capnp::byte>(pkt.data, (size_t)0),
        kj::arrayPtr<capnp::byte>(pkt.data, pkt.size));
      packet_counter++;
      av_packet_unref(&pkt);
    }
    return ret;
  }

  uint8_t *cy = convert_buf.data();
  uint8_t *cu = cy + in_width * in_height;
  uint8_t *cv = cu + (in_width / 2) * (in_height / 2);
  libyuv::NV12ToI420(buf->y, buf->stride,
                     buf->uv, buf->stride,
                     cy, in_width,
                     cu, in_width/2,
                     cv, in_width/2,
                     in_width, in_height);

  if (scaled) {
    uint8_t *out_y = downscale_buf.data();
    uint8_t *out_u = out_y + frame->width * frame->height;
    uint8_t *out_v = out_u + (frame->width / 2) * (frame->height / 2);
    libyuv::I420Scale(cy, in_width,
                      cu, in_width/2,
                      cv, in_width/2,
                      in_width, in_height,
                      out_y, frame->width,
                      out_u, frame->width/2,
                      out_v, frame->width/2,
                      frame->width, frame->height,
                      libyuv::kFilterNone);
    frame->data[0] = out_y;
    frame->data[1] = out_u;
    frame->data[2] = out_v;
  } else {
    frame->data[0] = cy;
    frame->data[1] = cu;
    frame->data[2] = cv;
  }
  frame->pts = frame_counter++;
  int ret = 0;

  int err = avcodec_send_frame(this->codec_ctx, frame);
  if (err < 0) {
    LOGE("avcodec_send_frame error %d", err);
    ret = -1;
  }

  AVPacket pkt = {};
  pkt.data = NULL;
  pkt.size = 0;
  while (ret >= 0) {
    err = avcodec_receive_packet(this->codec_ctx, &pkt);
    if (err == AVERROR_EOF) {
      break;
    } else if (err == AVERROR(EAGAIN)) {
      // Encoder might need a few frames on startup to get started. Keep going
      ret = 0;
      break;
    } else if (err < 0) {
      LOGE("avcodec_receive_packet error %d", err);
      ret = -1;
      break;
    }

    if (env_debug_encoder) {
      printf("%20s got %8d bytes flags %8x idx %4d id %8d\n", encoder_info.publish_name, pkt.size, pkt.flags, packet_counter, extra->frame_id);
    }

    publisher_publish(segment_num, packet_counter, *extra,
      (pkt.flags & AV_PKT_FLAG_KEY) ? V4L2_BUF_FLAG_KEYFRAME : 0,
      kj::arrayPtr<capnp::byte>(pkt.data, (size_t)0), // TODO: get the header
      kj::arrayPtr<capnp::byte>(pkt.data, pkt.size));

    packet_counter++;
  }
  av_packet_unref(&pkt);
  return ret;
}
