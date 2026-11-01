// cpp/include/pik2video/video_encoder.h
#ifndef PIK2VIDEO_VIDEO_ENCODER_H
#define PIK2VIDEO_VIDEO_ENCODER_H

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/pixfmt.h>
}

namespace pik2video {

// Обёртка над AVCodecContext для видео.
// Не знает про Muxer, FilterGraph или вход.
class VideoEncoder {
public:
    VideoEncoder() = default;
    ~VideoEncoder();

    VideoEncoder(const VideoEncoder&) = delete;
    VideoEncoder& operator=(const VideoEncoder&) = delete;

    bool open(int width, int height, int fps, int bitrate_kbps, int quality);
    int send(AVFrame* frame);
    int receive(AVPacket* pkt);
    void flush();
    void close();

    AVCodecContext* ctx() const { return ctx_; }
    AVRational time_base() const { return ctx_ ? ctx_->time_base : AVRational{1, 1000}; }

private:
    AVCodecContext* ctx_ = nullptr;
};

} // namespace pik2video

#endif // PIK2VIDEO_VIDEO_ENCODER_H
