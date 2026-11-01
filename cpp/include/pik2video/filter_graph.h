// cpp/include/pik2video/filter_graph.h
#ifndef PIK2VIDEO_FILTER_GRAPH_H
#define PIK2VIDEO_FILTER_GRAPH_H

extern "C" {
#include <libavfilter/avfilter.h>
#include <libavfilter/buffersink.h>
#include <libavfilter/buffersrc.h>
#include <libavutil/pixfmt.h>
}

namespace pik2video {

// Граф фильтров: buffer → crop + format → buffersink.
// Не знает про VideoInput, VideoEncoder или Muxer.
// Принимает уже нормализованные crop-параметры (чётные, в пределах источника).
class FilterGraph {
public:
    FilterGraph() = default;
    ~FilterGraph();

    FilterGraph(const FilterGraph&) = delete;
    FilterGraph& operator=(const FilterGraph&) = delete;

    bool open(int in_width, int in_height, AVPixelFormat in_pix_fmt,
              int crop_left, int crop_top, int crop_w, int crop_h,
              AVRational time_base);

    // Отправить кадр в фильтр.
    //  >= 0 — принято
    //  < 0  — ошибка
    int push(AVFrame* frame);

    // Забрать обработанный кадр.
    //  1  — есть кадр
    //  0  — пока нет (EAGAIN), попробуй позже
    //  <0  — ошибка / EOF
    int pull(AVFrame* frame);

    void close();

private:
    AVFilterGraph* graph_ = nullptr;
    AVFilterContext* src_ = nullptr;
    AVFilterContext* sink_ = nullptr;
};

} // namespace pik2video

#endif // PIK2VIDEO_FILTER_GRAPH_H
