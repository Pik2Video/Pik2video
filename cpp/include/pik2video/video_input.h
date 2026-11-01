// cpp/include/pik2video/video_input.h
#ifndef PIK2VIDEO_VIDEO_INPUT_H
#define PIK2VIDEO_VIDEO_INPUT_H

#include <string>

extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
}

namespace pik2video {

class SyncClock;

// Захват и декодирование видео с устройства (avfoundation на macOS).
// Не знает про энкодинг, фильтры и muxing.
// PTS каждого кадра выставляется по SyncClock — единый wall clock.
class VideoInput {
public:
    VideoInput() = default;
    ~VideoInput();

    VideoInput(const VideoInput&) = delete;
    VideoInput& operator=(const VideoInput&) = delete;

    // Открыть устройство и декодер. frame_tb — таймбаза для PTS
    // (совпадает с таймбазой фильтра и энкодера, обычно 1/1000).
    bool open(const char* device_name, int fps, SyncClock* clock, AVRational frame_tb);

    // Прочитать следующий декодированный кадр.
    //   1  — кадр есть, frame заполнен, frame->pts установлен
    //   0  — временно нет данных (EAGAIN), попробуй позже
    //  <0  — конец или ошибка
    int read_frame(AVFrame* frame);

    void close();

    // Найти индекс устройства захвата (1, 0, 2 или 3 на macOS).
    static std::string find_default_device();

private:
    // Регистрация avdevice (один раз на процесс). Вызывается перед любым
    // использованием av_find_input_format / avformat_open_input.
    static void ensure_avdevice();

public:

    int width() const { return width_; }
    int height() const { return height_; }
    AVPixelFormat pix_fmt() const { return pix_fmt_; }
    AVRational time_base() const { return time_base_; }

private:
    bool init_decoder();

    AVFormatContext* input_ctx_ = nullptr;
    AVCodecContext* dec_ctx_ = nullptr;
    AVStream* in_stream_ = nullptr;
    int video_stream_index_ = -1;
    AVRational time_base_{1, 1000000};
    AVRational frame_tb_{1, 1000};
    AVPacket* pkt_ = nullptr;
    SyncClock* clock_ = nullptr;

    int width_ = 0;
    int height_ = 0;
    AVPixelFormat pix_fmt_ = AV_PIX_FMT_NONE;
};

} // namespace pik2video

#endif // PIK2VIDEO_VIDEO_INPUT_H
