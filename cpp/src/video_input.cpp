// cpp/src/video_input.cpp
#include "pik2video/video_input.h"
#include "pik2video/sync_clock.h"

#include <cstring>
#include <iostream>
#include <string>

extern "C" {
#include <libavutil/opt.h>
#include <libavdevice/avdevice.h>
}

namespace pik2video {

VideoInput::~VideoInput() {
    close();
}

bool VideoInput::open(const char* device_name, int fps, SyncClock* clock, AVRational frame_tb) {
    ensure_avdevice();

    if (!device_name || !device_name[0]) {
        std::cerr << "VideoInput: empty device_name" << std::endl;
        return false;
    }
    if (!clock) {
        std::cerr << "VideoInput: clock is null" << std::endl;
        return false;
    }

    clock_ = clock;
    frame_tb_ = frame_tb;

    const AVInputFormat* input_format = nullptr;
#ifdef __APPLE__
    input_format = av_find_input_format("avfoundation");
#elif _WIN32
    input_format = av_find_input_format("dshow");
#elif __linux__
    input_format = av_find_input_format("x11grab");
#endif

    if (!input_format) {
        std::cerr << "VideoInput: input format not found" << std::endl;
        return false;
    }

    AVDictionary* opts = nullptr;
    std::string fps_str = std::to_string(fps);
    av_dict_set(&opts, "framerate", fps_str.c_str(), 0);
#ifdef __APPLE__
    // avfoundation: устройство обычно отдаёт uyvy422, просим явно
    av_dict_set(&opts, "pixel_format", "uyvy422", 0);
#endif

    int ret = avformat_open_input(&input_ctx_, device_name, input_format, &opts);
    av_dict_free(&opts);
    if (ret < 0) {
        std::cerr << "VideoInput: open device failed, code " << ret << std::endl;
        return false;
    }

    if (avformat_find_stream_info(input_ctx_, nullptr) < 0) {
        std::cerr << "VideoInput: find_stream_info failed" << std::endl;
        return false;
    }

    for (unsigned i = 0; i < input_ctx_->nb_streams; ++i) {
        if (input_ctx_->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
            video_stream_index_ = static_cast<int>(i);
            break;
        }
    }
    if (video_stream_index_ < 0) {
        std::cerr << "VideoInput: no video stream" << std::endl;
        return false;
    }

    in_stream_ = input_ctx_->streams[video_stream_index_];
    time_base_ = in_stream_->time_base;

    if (!init_decoder()) {
        return false;
    }

    pkt_ = av_packet_alloc();
    if (!pkt_) {
        std::cerr << "VideoInput: packet alloc failed" << std::endl;
        return false;
    }

    return true;
}

bool VideoInput::init_decoder() {
    AVCodecParameters* codecpar = in_stream_->codecpar;

    const AVCodec* dec = avcodec_find_decoder(codecpar->codec_id);
    if (!dec) {
        std::cerr << "VideoInput: decoder not found" << std::endl;
        return false;
    }

    dec_ctx_ = avcodec_alloc_context3(dec);
    if (!dec_ctx_) {
        std::cerr << "VideoInput: decoder alloc failed" << std::endl;
        return false;
    }
    if (avcodec_parameters_to_context(dec_ctx_, codecpar) < 0) {
        std::cerr << "VideoInput: params_to_context failed" << std::endl;
        return false;
    }
    if (avcodec_open2(dec_ctx_, dec, nullptr) < 0) {
        std::cerr << "VideoInput: open decoder failed" << std::endl;
        return false;
    }

    width_ = dec_ctx_->width;
    height_ = dec_ctx_->height;
    pix_fmt_ = dec_ctx_->pix_fmt;
    return true;
}

int VideoInput::read_frame(AVFrame* frame) {
    if (!input_ctx_ || !dec_ctx_ || !pkt_ || !clock_) {
        return -1;
    }

    for (;;) {
        // Сначала попытаться забрать уже декодированный кадр
        int ret = avcodec_receive_frame(dec_ctx_, frame);
        if (ret == 0) {
            frame->pts = clock_->now_pts(frame_tb_);
            return 1;
        }
        if (ret != AVERROR(EAGAIN)) {
            return ret < 0 ? ret : -1;
        }

        // Кадров нет — читаем следующий пакет с устройства
        ret = av_read_frame(input_ctx_, pkt_);
        if (ret == AVERROR(EAGAIN)) {
            return 0;                     // временно нет данных
        }
        if (ret < 0) {
            return ret;                   // конец или ошибка
        }

        if (pkt_->stream_index != video_stream_index_) {
            av_packet_unref(pkt_);
            continue;
        }

        ret = avcodec_send_packet(dec_ctx_, pkt_);
        av_packet_unref(pkt_);
        if (ret < 0 && ret != AVERROR(EAGAIN)) {
            return ret;
        }
    }
}

void VideoInput::close() {
    if (pkt_) {
        av_packet_free(&pkt_);
        pkt_ = nullptr;
    }
    if (dec_ctx_) {
        avcodec_free_context(&dec_ctx_);
        dec_ctx_ = nullptr;
    }
    if (input_ctx_) {
        avformat_close_input(&input_ctx_);
        input_ctx_ = nullptr;
    }
    in_stream_ = nullptr;
    video_stream_index_ = -1;
    width_ = 0;
    height_ = 0;
    pix_fmt_ = AV_PIX_FMT_NONE;
    clock_ = nullptr;
}

void VideoInput::ensure_avdevice() {
    static bool initialized = false;
    if (!initialized) {
        avdevice_register_all();
        initialized = true;
    }
}

std::string VideoInput::find_default_device() {
    ensure_avdevice();

#ifdef __APPLE__
    // avfoundation: перебор индексов устройств, обычно экран — 1 или 0
    const char* devices[] = {"1", "0", "2", "3"};
    for (const char* dev : devices) {
        AVFormatContext* test_ctx = nullptr;
        const AVInputFormat* fmt = av_find_input_format("avfoundation");
        if (fmt && avformat_open_input(&test_ctx, dev, fmt, nullptr) == 0) {
            avformat_close_input(&test_ctx);
            return dev;
        }
    }
    return "1"; // fallback
#elif _WIN32
    return "video=screen-capture-recorder";
#elif __linux__
    return ":0.0";
#else
    return "";
#endif
}

} // namespace pik2video
