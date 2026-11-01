// cpp/src/filter_graph.cpp
#include "pik2video/filter_graph.h"

#include <cstdio>
#include <iostream>

extern "C" {
#include <libavutil/opt.h>
}

namespace pik2video {

FilterGraph::~FilterGraph() {
    close();
}

bool FilterGraph::open(int in_width, int in_height, AVPixelFormat in_pix_fmt,
                       int crop_left, int crop_top, int crop_w, int crop_h,
                       AVRational time_base) {
    close();

    graph_ = avfilter_graph_alloc();
    if (!graph_) {
        std::cerr << "FilterGraph: graph alloc failed" << std::endl;
        return false;
    }

    const AVFilter* buffersrc = avfilter_get_by_name("buffer");
    const AVFilter* buffersink = avfilter_get_by_name("buffersink");
    if (!buffersrc || !buffersink) {
        std::cerr << "FilterGraph: buffer filter not found" << std::endl;
        close();
        return false;
    }

    char args[512];
    snprintf(args, sizeof(args),
        "video_size=%dx%d:pix_fmt=%d:time_base=%d/%d:pixel_aspect=1/1",
        in_width, in_height, static_cast<int>(in_pix_fmt),
        time_base.num, time_base.den);

    if (avfilter_graph_create_filter(&src_, buffersrc, "in", args, nullptr, graph_) < 0) {
        std::cerr << "FilterGraph: create source failed" << std::endl;
        close();
        return false;
    }

    if (avfilter_graph_create_filter(&sink_, buffersink, "out", nullptr, nullptr, graph_) < 0) {
        std::cerr << "FilterGraph: create sink failed" << std::endl;
        close();
        return false;
    }

    enum AVPixelFormat pix_fmts[] = { AV_PIX_FMT_YUV420P, AV_PIX_FMT_NONE };
    av_opt_set_bin(sink_, "pix_fmts", reinterpret_cast<const uint8_t*>(pix_fmts),
                   sizeof(pix_fmts) - sizeof(pix_fmts[0]), AV_OPT_SEARCH_CHILDREN);

    char filter_desc[512];
    snprintf(filter_desc, sizeof(filter_desc),
        "crop=%d:%d:%d:%d,format=yuv420p",
        crop_w, crop_h, crop_left, crop_top);

    AVFilterInOut* outputs = avfilter_inout_alloc();
    AVFilterInOut* inputs = avfilter_inout_alloc();
    outputs->name = av_strdup("in");
    outputs->filter_ctx = src_;
    outputs->pad_idx = 0;
    outputs->next = nullptr;

    inputs->name = av_strdup("out");
    inputs->filter_ctx = sink_;
    inputs->pad_idx = 0;
    inputs->next = nullptr;

    if (avfilter_graph_parse_ptr(graph_, filter_desc, &inputs, &outputs, nullptr) < 0) {
        std::cerr << "FilterGraph: parse failed" << std::endl;
        avfilter_inout_free(&outputs);
        avfilter_inout_free(&inputs);
        close();
        return false;
    }
    avfilter_inout_free(&outputs);
    avfilter_inout_free(&inputs);

    if (avfilter_graph_config(graph_, nullptr) < 0) {
        std::cerr << "FilterGraph: config failed" << std::endl;
        close();
        return false;
    }

    return true;
}

int FilterGraph::push(AVFrame* frame) {
    if (!src_) return -1;
    return av_buffersrc_write_frame(src_, frame);
}

int FilterGraph::pull(AVFrame* frame) {
    if (!sink_) return -1;
    int ret = av_buffersink_get_frame(sink_, frame);
    if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) return 0;
    if (ret < 0) return ret;
    return 1;
}

void FilterGraph::close() {
    if (graph_) {
        avfilter_graph_free(&graph_);
        graph_ = nullptr;
    }
    src_ = nullptr;
    sink_ = nullptr;
}

} // namespace pik2video
