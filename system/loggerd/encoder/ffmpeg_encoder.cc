#include "system/loggerd/encoder/ffmpeg_encoder.h"

#include <fcntl.h>
#include <unistd.h>

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

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

namespace {

int getenv_int(const char *name, int default_val) {
  const char *v = getenv(name);
  if (v == nullptr || v[0] == '\0') return default_val;
  return atoi(v);
}

const char *getenv_str(const char *name, const char *default_val) {
  const char *v = getenv(name);
  if (v == nullptr || v[0] == '\0') return default_val;
  return v;
}

}  // namespace

FfmpegEncoder::FfmpegEncoder(const EncoderInfo &encoder_info, int in_width, int in_height)
    : VideoEncoder(encoder_info, in_width, in_height) {
  frame = av_frame_alloc();
  assert(frame);

  auto encode_type = encoder_info.get_settings(in_width).encode_type;
  frame->format = (encode_type == cereal::EncodeIndex::Type::FULL_H_E_V_C) ? AV_PIX_FMT_NV12 : AV_PIX_FMT_YUV420P;
  frame->width = out_width;
  frame->height = out_height;
  frame->linesize[0] = out_width;
  frame->linesize[1] = out_width / 2;
  frame->linesize[2] = out_width / 2;

  convert_buf.resize(in_width * in_height * 3 / 2);

  if (in_width != out_width || in_height != out_height) {
    downscale_buf.resize(out_width * out_height * 3 / 2);
  }
}

FfmpegEncoder::~FfmpegEncoder() {
  encoder_close();
  av_frame_free(&frame);
}

void FfmpegEncoder::encoder_open() {
  auto encode_type = encoder_info.get_settings(in_width).encode_type;

  const AVCodec *codec = nullptr;
  if (encode_type == cereal::EncodeIndex::Type::QCAMERA_H264) {
    codec = avcodec_find_encoder(AV_CODEC_ID_H264);
  } else if (encode_type == cereal::EncodeIndex::Type::FULL_H_E_V_C) {
    codec = avcodec_find_encoder_by_name("hevc_vaapi");
  } else {
    codec = avcodec_find_encoder(AV_CODEC_ID_FFVHUFF);
  }
  assert(codec);

  this->codec_ctx = avcodec_alloc_context3(codec);
  assert(this->codec_ctx);
  this->codec_ctx->width = frame->width;
  this->codec_ctx->height = frame->height;
  this->codec_ctx->time_base = (AVRational){1, encoder_info.fps};
  this->codec_ctx->framerate = (AVRational){encoder_info.fps, 1};

  int err = 0;
  if (encode_type == cereal::EncodeIndex::Type::FULL_H_E_V_C) {
    this->codec_ctx->pix_fmt = AV_PIX_FMT_VAAPI;
    this->codec_ctx->max_b_frames = 0;
    this->codec_ctx->gop_size = encoder_info.fps * 2;

    err = av_hwdevice_ctx_create(&this->codec_ctx->hw_device_ctx,
                                 AV_HWDEVICE_TYPE_VAAPI,
                                 "/dev/dri/renderD128",
                                 nullptr, 0);
    assert(err >= 0);

    AVBufferRef *hw_frames_ref = av_hwframe_ctx_alloc(this->codec_ctx->hw_device_ctx);
    assert(hw_frames_ref);

    auto *frames_ctx = (AVHWFramesContext *)hw_frames_ref->data;
    frames_ctx->format = AV_PIX_FMT_VAAPI;
    frames_ctx->sw_format = AV_PIX_FMT_NV12;
    frames_ctx->width = frame->width;
    frames_ctx->height = frame->height;
    frames_ctx->initial_pool_size = 20;

    err = av_hwframe_ctx_init(hw_frames_ref);
    assert(err >= 0);

    this->codec_ctx->hw_frames_ctx = av_buffer_ref(hw_frames_ref);
    av_buffer_unref(&hw_frames_ref);
    assert(this->codec_ctx->hw_frames_ctx);

    av_opt_set(this->codec_ctx->priv_data, "profile", "main", 0);
    av_opt_set(this->codec_ctx->priv_data, "tier", "main", 0);
    av_opt_set(this->codec_ctx->priv_data, "level", "5.0", 0);
    av_opt_set(this->codec_ctx->priv_data, "rc_mode", getenv_str("HEVC_VAAPI_RC_MODE", "CBR"), 0);
    this->codec_ctx->bit_rate = getenv_int("HEVC_VAAPI_BITRATE", 2500000);

    const int low_power = getenv_int("HEVC_VAAPI_LOW_POWER", -1);
    if (low_power >= 0) {
      av_opt_set_int(this->codec_ctx->priv_data, "low_power", low_power, 0);
    }
    const int async_depth = getenv_int("HEVC_VAAPI_ASYNC_DEPTH", -1);
    if (async_depth > 0) {
      av_opt_set_int(this->codec_ctx->priv_data, "async_depth", async_depth, 0);
    }
  } else {
    this->codec_ctx->pix_fmt = AV_PIX_FMT_YUV420P;
    auto qcam_settings = encoder_info.get_settings(in_width);
    this->codec_ctx->max_b_frames = qcam_settings.b_frames;
    this->codec_ctx->gop_size = qcam_settings.gop_size;
    this->codec_ctx->bit_rate = qcam_settings.bitrate;
    this->codec_ctx->flags |= AV_CODEC_FLAG_LOW_DELAY;

    av_opt_set(this->codec_ctx->priv_data, "preset", getenv_str("QCAMERA_X264_PRESET", "ultrafast"), 0);
    av_opt_set(this->codec_ctx->priv_data, "tune", getenv_str("QCAMERA_X264_TUNE", "zerolatency"), 0);
  }

  err = avcodec_open2(this->codec_ctx, codec, NULL);
  assert(err >= 0);

  is_open = true;
  segment_num++;
  counter = 0;
}

void FfmpegEncoder::encoder_close() {
  if (!is_open) return;

  avcodec_free_context(&codec_ctx);
  is_open = false;
}

int FfmpegEncoder::encode_frame(VisionBuf* buf, VisionIpcBufExtra *extra) {
  assert(buf->width == this->in_width);
  assert(buf->height == this->in_height);

  auto encode_type = encoder_info.get_settings(in_width).encode_type;

  if (encode_type == cereal::EncodeIndex::Type::FULL_H_E_V_C) {
    const uint8_t *src_y = buf->y;
    const uint8_t *src_uv = buf->uv;
    int src_stride_y = buf->stride;
    int src_stride_uv = buf->stride;

    if (downscale_buf.size() > 0) {
      uint8_t *dst_y = downscale_buf.data();
      uint8_t *dst_uv = dst_y + frame->width * frame->height;
      libyuv::ScalePlane(buf->y, buf->stride,
                         in_width, in_height,
                         dst_y, frame->width,
                         frame->width, frame->height,
                         libyuv::kFilterNone);
      libyuv::ScalePlane(buf->uv, buf->stride,
                         in_width, in_height / 2,
                         dst_uv, frame->width,
                         frame->width, frame->height / 2,
                         libyuv::kFilterNone);

      src_y = dst_y;
      src_uv = dst_uv;
      src_stride_y = frame->width;
      src_stride_uv = frame->width;
    }

    frame->format = AV_PIX_FMT_NV12;
    frame->data[0] = const_cast<uint8_t *>(src_y);
    frame->data[1] = const_cast<uint8_t *>(src_uv);
    frame->data[2] = nullptr;
    frame->linesize[0] = src_stride_y;
    frame->linesize[1] = src_stride_uv;
    frame->linesize[2] = 0;
    frame->pts = counter;

    AVFrame *hw_frame = av_frame_alloc();
    assert(hw_frame);

    int err = av_hwframe_get_buffer(this->codec_ctx->hw_frames_ctx, hw_frame, 0);
    assert(err >= 0);

    err = av_hwframe_transfer_data(hw_frame, frame, 0);
    assert(err >= 0);

    hw_frame->pts = frame->pts;

    int ret = counter;

    err = avcodec_send_frame(this->codec_ctx, hw_frame);
    av_frame_free(&hw_frame);

    if (err < 0) {
      LOGE("avcodec_send_frame (VAAPI HEVC) error %d", err);
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
        LOGE("avcodec_receive_packet (VAAPI HEVC) error %d", err);
        ret = -1;
        break;
      }

      if (env_debug_encoder) {
        printf("%20s got %8d bytes flags %8x idx %4d id %8d\n",
               encoder_info.publish_name, pkt.size, pkt.flags, counter, extra->frame_id);
      }

      publisher_publish(segment_num, counter, *extra,
        (pkt.flags & AV_PKT_FLAG_KEY) ? V4L2_BUF_FLAG_KEYFRAME : 0,
        kj::arrayPtr<capnp::byte>(pkt.data, (size_t)0),
        kj::arrayPtr<capnp::byte>(pkt.data, pkt.size));

      counter++;
      av_packet_unref(&pkt);
    }
    av_packet_unref(&pkt);
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

  if (downscale_buf.size() > 0) {
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
  // PTS is expressed in codec_ctx->time_base units (1/fps). Using the frame
  // index keeps monotonic timestamps and avoids mpegts timestamp regressions.
  frame->pts = counter;

  int ret = counter;

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
      printf("%20s got %8d bytes flags %8x idx %4d id %8d\n", encoder_info.publish_name, pkt.size, pkt.flags, counter, extra->frame_id);
    }

    publisher_publish(segment_num, counter, *extra,
      (pkt.flags & AV_PKT_FLAG_KEY) ? V4L2_BUF_FLAG_KEYFRAME : 0,
      kj::arrayPtr<capnp::byte>(pkt.data, (size_t)0), // TODO: get the header
      kj::arrayPtr<capnp::byte>(pkt.data, pkt.size));

    counter++;
  }
  av_packet_unref(&pkt);
  return ret;
}
