// cpp/src/sync_clock.cpp
#include "pik2video/sync_clock.h"

extern "C" {
#include <libavutil/time.h>
}

namespace pik2video {

void SyncClock::start() {
    start_time_ = Clock::now();
    start_epoch_ns_ = av_gettime_relative();
    frame_count_.store(0);
    started_.store(true);
}

int64_t SyncClock::elapsed_us() const {
    if (!started_.load()) return 0;
    auto now = Clock::now();
    return std::chrono::duration_cast<std::chrono::microseconds>(now - start_time_).count();
}

int64_t SyncClock::now_pts(AVRational tb) const {
    int64_t us = elapsed_us();
    return av_rescale_q(us, AVRational{1, 1000000}, tb);
}

int64_t SyncClock::start_epoch_ns() const {
    return start_epoch_ns_;
}

int32_t SyncClock::increment_frame_count() {
    return frame_count_.fetch_add(1) + 1;
}

int32_t SyncClock::frame_count() const {
    return frame_count_.load();
}

bool SyncClock::is_started() const {
    return started_.load();
}

} // namespace pik2video
