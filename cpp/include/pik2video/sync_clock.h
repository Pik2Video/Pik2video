// cpp/include/pik2video/sync_clock.h
#ifndef PIK2VIDEO_SYNC_CLOCK_H
#define PIK2VIDEO_SYNC_CLOCK_H

#include <atomic>
#include <chrono>
#include <cstdint>

extern "C" {
#include <libavutil/avutil.h>
}

namespace pik2video {

// Единый источник времени для видео и звука.
// Все PTS считаются от одного старта, поэтому синхронизация точная by design.
class SyncClock {
public:
    SyncClock() = default;
    ~SyncClock() = default;

    void start();
    int64_t elapsed_us() const;
    int64_t now_pts(AVRational tb) const;
    int64_t start_epoch_ns() const;

    int32_t increment_frame_count();
    int32_t frame_count() const;
    bool is_started() const;

private:
    using Clock = std::chrono::steady_clock;
    Clock::time_point start_time_{};
    int64_t start_epoch_ns_ = 0;
    std::atomic<int32_t> frame_count_{0};
    std::atomic<bool> started_{false};
};

} // namespace pik2video

#endif // PIK2VIDEO_SYNC_CLOCK_H
