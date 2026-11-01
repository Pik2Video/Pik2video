// cpp/src/muxer.cpp
#include "pik2video/muxer.h"

#include <iostream>

namespace pik2video {

Muxer::~Muxer() {
    close();
}

bool Muxer::open(const char* output_path) {
    close();
    output_path_ = output_path ? output_path : "";

    int ret = avformat_alloc_output_context2(&fmt_ctx_, nullptr, "mp4", output_path_.c_str());
    if (ret < 0 || !fmt_ctx_) {
        std::cerr << "Muxer: alloc output context failed" << std::endl;
        return false;
    }
    return true;
}

bool Muxer::add_stream(AVCodecContext* enc_ctx) {
    if (!fmt_ctx_ || !enc_ctx) return false;

    stream_ = avformat_new_stream(fmt_ctx_, enc_ctx->codec);
    if (!stream_) {
        std::cerr << "Muxer: new stream failed" << std::endl;
        return false;
    }

    avcodec_parameters_from_context(stream_->codecpar, enc_ctx);
    stream_->time_base = enc_ctx->time_base;
    return true;
}

bool Muxer::write_header() {
    if (!fmt_ctx_ || !stream_) return false;

    if (!(fmt_ctx_->oformat->flags & AVFMT_NOFILE)) {
        if (avio_open(&fmt_ctx_->pb, output_path_.c_str(), AVIO_FLAG_WRITE) < 0) {
            std::cerr << "Muxer: avio_open failed" << std::endl;
            return false;
        }
    }

    if (avformat_write_header(fmt_ctx_, nullptr) < 0) {
        std::cerr << "Muxer: write_header failed" << std::endl;
        return false;
    }
    return true;
}

bool Muxer::write_packet(AVPacket* pkt) {
    if (!fmt_ctx_) return false;
    return av_interleaved_write_frame(fmt_ctx_, pkt) >= 0;
}

bool Muxer::write_trailer() {
    if (!fmt_ctx_) return false;
    return av_write_trailer(fmt_ctx_) >= 0;
}

void Muxer::close() {
    if (fmt_ctx_) {
        if (fmt_ctx_->pb) {
            avio_closep(&fmt_ctx_->pb);
        }
        avformat_free_context(fmt_ctx_);
        fmt_ctx_ = nullptr;
    }
    stream_ = nullptr;
    output_path_.clear();
}

} // namespace pik2video
