// cpp/recorder.cpp
#include "recorder.h"
#include "pik2video/sync_clock.h"
#include "pik2video/video_input.h"
#include "pik2video/filter_graph.h"
#include "pik2video/video_encoder.h"
#include "pik2video/muxer.h"
#include <iostream>
#include <chrono>
#include <thread>
#include <atomic>
#include <mutex>
#include <string>
#include <memory>
#include <cstring>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/avutil.h>
}

// -----------------------------------------------------------------------------
// Класс Recorder – инкапсулирует всю логику записи
// -----------------------------------------------------------------------------
class Recorder {
public:
    Recorder(const Pik2VideoParams* params);
    ~Recorder();

    // Запуск записи (блокирующий, вызывается в отдельном потоке)
    void run();

    // Остановка записи
    void stop();

    // Получение статистики
    double elapsed_time() const;
    int frame_count() const;

    // Проверка, запущена ли запись
    bool is_running() const { return running_; }

private:
    // Параметры записи
    struct Params {
        std::string output_path;
        int left, top, width, height;
        int fps;
        int bitrate_kbps = 8000;      // по умолчанию 8 Мбит/с
        int quality = 75;             // для аппаратных энкодеров (0-100)
    } params_;

    // Состояние
    std::atomic<bool> running_{false};
    pik2video::SyncClock clock_;

    // Захват видео (RAII)
    std::unique_ptr<pik2video::VideoInput> video_input_;

    // FFmpeg объекты (RAII)
    std::unique_ptr<pik2video::VideoEncoder> encoder_;
    std::unique_ptr<pik2video::Muxer> muxer_;
    std::unique_ptr<pik2video::FilterGraph> filter_;

    // Приватные методы
    bool init_output();
    bool init_filters();
    void cleanup();

};

// -----------------------------------------------------------------------------
// Реализация Recorder
// -----------------------------------------------------------------------------

Recorder::Recorder(const Pik2VideoParams* p)
    : params_{{p && p->output_dir ? std::string(p->output_dir) + "/output.mp4" : std::string()},
              p ? p->left : 0, p ? p->top : 0,
              p ? p->width : 0, p ? p->height : 0,
              p ? p->fps : 30,
              p && p->bitrate_kbps > 0 ? p->bitrate_kbps : 8000,
              p && p->quality > 0 ? p->quality : 75}
{
    // avformat: сетевая инициализация (avdevice — в VideoInput)
    static bool initialized = false;
    if (!initialized) {
        avformat_network_init();
        initialized = true;
    }
}

Recorder::~Recorder() {
    cleanup();
}

void Recorder::run() {
    if (running_) return;

    // 1. Инициализация (сначала выход — нужен encoder_->time_base() для PTS)
    if (!init_output()) {
        std::cerr << "Ошибка инициализации выхода" << std::endl;
        cleanup();
        return;
    }

    video_input_ = std::make_unique<pik2video::VideoInput>();
    std::string device_name = pik2video::VideoInput::find_default_device();
    if (!video_input_->open(device_name.c_str(), params_.fps, &clock_, encoder_->time_base())) {
        std::cerr << "Ошибка инициализации входа" << std::endl;
        cleanup();
        return;
    }

    if (!init_filters()) {
        std::cerr << "Ошибка инициализации фильтров" << std::endl;
        cleanup();
        return;
    }

    // 2. Запуск
    running_ = true;
    clock_.start();

    // 3. Основной цикл
    AVFrame* decoded_frame = av_frame_alloc();
    AVFrame* filtered_frame = av_frame_alloc();
    if (!decoded_frame || !filtered_frame) {
        std::cerr << "Ошибка выделения памяти" << std::endl;
        cleanup();
        return;
    }

    // Таймер для ограничения FPS
    auto next_frame_time = std::chrono::steady_clock::now();

    while (running_) {
        // Читаем декодированный кадр с устройства (PTS проставлен в VideoInput)
        int ret = video_input_->read_frame(decoded_frame);
        if (ret == 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            continue;
        }
        if (ret < 0) {
            if (running_) {
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
            continue;
        }

        // Ограничение FPS: пропускаем кадр, если ещё не пришло время
        auto now = std::chrono::steady_clock::now();
        if (now < next_frame_time) {
            av_frame_unref(decoded_frame);
            continue;
        }
        next_frame_time += std::chrono::milliseconds(1000 / params_.fps);

        // Отправляем кадр в фильтр
        if (filter_->push(decoded_frame) < 0) {
            std::cerr << "Ошибка отправки кадра в фильтр" << std::endl;
            av_frame_unref(decoded_frame);
            continue;
        }
        av_frame_unref(decoded_frame);

        // Получаем обработанные кадры из фильтра
        while (true) {
            ret = filter_->pull(filtered_frame);
            if (ret == 0) {
                break;
            } else if (ret < 0) {
                std::cerr << "Ошибка получения кадра из фильтра" << std::endl;
                break;
            }

            // Кодируем кадр (filtered_frame->pts уже установлен фильтр-графом)
            if (encoder_->send(filtered_frame) == 0) {
                AVPacket* out_pkt = av_packet_alloc();
                while (encoder_->receive(out_pkt) == 1) {
                    av_packet_rescale_ts(out_pkt, encoder_->time_base(), muxer_->stream()->time_base);
                    out_pkt->stream_index = muxer_->stream()->index;
                    muxer_->write_packet(out_pkt);
                    av_packet_unref(out_pkt);
                }
                av_packet_free(&out_pkt);
            }
            clock_.increment_frame_count();
            av_frame_unref(filtered_frame);
        }
    }

    // 4. Финализация (отправляем пустой кадр в кодировщик)
    encoder_->flush();
    AVPacket* out_pkt = av_packet_alloc();
    while (encoder_->receive(out_pkt) == 1) {
        av_packet_rescale_ts(out_pkt, encoder_->time_base(), muxer_->stream()->time_base);
        out_pkt->stream_index = muxer_->stream()->index;
        muxer_->write_packet(out_pkt);
        av_packet_unref(out_pkt);
    }
    av_packet_free(&out_pkt);

    // 5. Запись трейлера и закрытие
    muxer_->write_trailer();

    // 6. Очистка
    av_frame_free(&decoded_frame);
    av_frame_free(&filtered_frame);
    cleanup();

    std::cout << "Запись завершена. Кадров: " << clock_.frame_count() << std::endl;
}

void Recorder::stop() {
    running_ = false;
}

double Recorder::elapsed_time() const {
    if (!running_) return 0.0;
    return clock_.elapsed_us() / 1000000.0;
}

int Recorder::frame_count() const {
    return clock_.frame_count();
}

// ---------- Инициализация выхода ----------
bool Recorder::init_output() {
    encoder_ = std::make_unique<pik2video::VideoEncoder>();
    if (!encoder_->open(params_.width, params_.height, params_.fps,
                        params_.bitrate_kbps, params_.quality)) {
        std::cerr << "Ошибка открытия кодера" << std::endl;
        return false;
    }

    muxer_ = std::make_unique<pik2video::Muxer>();
    if (!muxer_->open(params_.output_path.c_str())) {
        std::cerr << "Ошибка создания выходного контекста" << std::endl;
        return false;
    }

    if (!muxer_->add_stream(encoder_->ctx())) {
        std::cerr << "Ошибка создания выходного потока" << std::endl;
        return false;
    }

    if (!muxer_->write_header()) {
        std::cerr << "Ошибка записи заголовка" << std::endl;
        return false;
    }

    return true;
}

// ---------- Инициализация фильтров ----------
bool Recorder::init_filters() {
    if (!video_input_) {
        std::cerr << "init_filters: video_input is null" << std::endl;
        return false;
    }

    int cl = params_.left;
    int ct = params_.top;
    if (cl % 2 != 0) cl--;
    if (ct % 2 != 0) ct--;
    int cw = params_.width;
    int ch = params_.height;
    if (cw % 2 != 0) cw--;
    if (ch % 2 != 0) ch--;
    if (cl + cw > video_input_->width()) cw = video_input_->width() - cl;
    if (ct + ch > video_input_->height()) ch = video_input_->height() - ct;

    filter_ = std::make_unique<pik2video::FilterGraph>();
    return filter_->open(video_input_->width(), video_input_->height(),
                          video_input_->pix_fmt(), cl, ct, cw, ch,
                          encoder_->time_base());
}

// ---------- Очистка ресурсов ----------
void Recorder::cleanup() {
    if (video_input_) {
        video_input_->close();
        video_input_.reset();
    }
    if (muxer_) {
        muxer_->close();
        muxer_.reset();
    }
    if (encoder_) {
        encoder_->close();
        encoder_.reset();
    }
    if (filter_) {
        filter_->close();
        filter_.reset();
    }
}

// ---------- Определение устройства ----------

// ---------- Выбор кодера ----------
// -----------------------------------------------------------------------------
// Глобальные переменные для управления одной сессией
// -----------------------------------------------------------------------------
static std::unique_ptr<Recorder> g_recorder;
static std::thread g_recording_thread;
static std::mutex g_mutex;

// -----------------------------------------------------------------------------
// Экспортируемые C-функции
// -----------------------------------------------------------------------------
extern "C" {

int recorder_start(const Pik2VideoParams* params) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (!params || !params->output_dir) {
        std::cerr << "recorder_start: params is null" << std::endl;
        return -2;
    }

    if (g_recorder && g_recorder->is_running()) {
        std::cerr << "Запись уже запущена" << std::endl;
        return -1;
    }

    g_recorder = std::make_unique<Recorder>(params);

    // Запускаем поток
    g_recording_thread = std::thread([&]() {
        g_recorder->run();
    });

    return 0;
}

void recorder_stop() {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_recorder) {
        g_recorder->stop();
        if (g_recording_thread.joinable()) {
            g_recording_thread.join();
        }
        g_recorder.reset();
    }
}

double recorder_get_elapsed_time() {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_recorder) {
        return g_recorder->elapsed_time();
    }
    return 0.0;
}

int recorder_get_frame_count() {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_recorder) {
        return g_recorder->frame_count();
    }
    return 0;
}

} // extern "C"