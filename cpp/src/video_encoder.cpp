// cpp/src/video_encoder.cpp
#include "pik2video/video_encoder.h"

#include <cstring>
#include <iostream>
#include <string>

extern "C" {
#include <libavutil/opt.h>
#include <libavutil/error.h>
}

namespace pik2video {

namespace {

const AVCodec* pick_encoder() {
    const AVCodec* enc = avcodec_find_encoder_by_name("h264_videotoolbox");
#ifdef _WIN32
    enc = avcodec_find_encoder_by_name("h264_nvenc");
    if (!enc) enc = avcodec_find_encoder_by_name("h264_amf");
#endif
#ifdef __linux__
    enc = avcodec_find_encoder_by_name("h264_nvenc");
    if (!enc) enc = avcodec_find_encoder_by_name("h264_vaapi");
#endif
    if (!enc) {
        enc = avcodec_find_encoder(AV_CODEC_ID_H264);
    }
    return enc;
}

} // namespace

VideoEncoder::~VideoEncoder() {
    close();
}

bool VideoEncoder::open(int width, int height, int fps, int bitrate_kbps, int quality) {
    close();

    const AVCodec* enc = pick_encoder();
    if (!enc) {
        std::cerr << "VideoEncoder: codec not found" << std::endl;
        return false;
    }

    ctx_ = avcodec_alloc_context3(enc);
    if (!ctx_) {
        std::cerr << "VideoEncoder: ctx alloc failed" << std::endl;
        return false;
    }

    ctx_->codec_type = AVMEDIA_TYPE_VIDEO;
    ctx_->width = width;
    ctx_->height = height;
    ctx_->time_base = AVRational{1, 1000};
    ctx_->framerate = AVRational{fps, 1};
    ctx_->pix_fmt = AV_PIX_FMT_YUV420P;

    if (enc->id == AV_CODEC_ID_H264) {
        if (strcmp(enc->name, "h264_videotoolbox") == 0) {
            // videotoolbox смотрит на avctx->bit_rate, а не на priv_data.
            if (bitrate_kbps > 0) {
                ctx_->bit_rate = static_cast<int64_t>(bitrate_kbps) * 1000;
                ctx_->rc_max_rate = ctx_->bit_rate;
                ctx_->rc_buffer_size = static_cast<int>(ctx_->bit_rate * 2);   // 2 сек буфер
            } else if (quality > 0) {
                av_opt_set(ctx_->priv_data, "quality",
                           std::to_string(quality).c_str(), 0);
            }
            av_opt_set(ctx_->priv_data, "allow_sw", "1", 0);
        } else {
            ctx_->bit_rate = static_cast<int64_t>(bitrate_kbps) * 1000;
            av_opt_set(ctx_->priv_data, "preset", "medium", 0);
            av_opt_set(ctx_->priv_data, "crf", "23", 0);
        }
    }

    std::cerr << "VideoEncoder: encoder=" << enc->name
              << ", target bitrate=" << bitrate_kbps << " kbps"
              << ", ctx->bit_rate=" << ctx_->bit_rate << " bps"
              << ", quality=" << quality << std::endl;

    if (avcodec_open2(ctx_, enc, nullptr) < 0) {
        std::cerr << "VideoEncoder: open codec failed" << std::endl;
        close();
        return false;
    }

    return true;
}

int VideoEncoder::send(AVFrame* frame) {
    if (!ctx_) return -1;
    return avcodec_send_frame(ctx_, frame);
}

int VideoEncoder::receive(AVPacket* pkt) {
    if (!ctx_) return -1;
    int ret = avcodec_receive_packet(ctx_, pkt);
    if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) return 0;
    if (ret < 0) return ret;
    return 1;
}

void VideoEncoder::flush() {
    if (ctx_) {
        avcodec_send_frame(ctx_, nullptr);
    }
}

void VideoEncoder::close() {
    if (ctx_) {
        avcodec_free_context(&ctx_);
        ctx_ = nullptr;
    }
}

} // namespace pik2video
