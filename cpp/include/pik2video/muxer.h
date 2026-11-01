// cpp/include/pik2video/muxer.h
#ifndef PIK2VIDEO_MUXER_H
#define PIK2VIDEO_MUXER_H

#include <string>

extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
}

namespace pik2video {

// Обёртка над AVFormatContext: открытие файла, потоки, запись пакетов.
class Muxer {
public:
    Muxer() = default;
    ~Muxer();

    Muxer(const Muxer&) = delete;
    Muxer& operator=(const Muxer&) = delete;

    bool open(const char* output_path);
    bool add_stream(AVCodecContext* enc_ctx);
    bool write_header();
    bool write_packet(AVPacket* pkt);
    bool write_trailer();
    void close();

    AVStream* stream() const { return stream_; }
    AVFormatContext* ctx() const { return fmt_ctx_; }

private:
    AVFormatContext* fmt_ctx_ = nullptr;
    AVStream* stream_ = nullptr;
    std::string output_path_;
};

} // namespace pik2video

#endif // PIK2VIDEO_MUXER_H
