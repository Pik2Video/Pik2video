// cpp/recorder.cpp
#include "recorder.h"
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
#include <libavutil/opt.h>
#include <libavutil/time.h>
#include <libswscale/swscale.h>
#include <libavdevice/avdevice.h>
#include <libavfilter/avfilter.h>
#include <libavfilter/buffersink.h>
#include <libavfilter/buffersrc.h>
}

// -----------------------------------------------------------------------------
// Класс Recorder – инкапсулирует всю логику записи
// -----------------------------------------------------------------------------
class Recorder {
public:
    Recorder(const std::string& output_dir, int left, int top, int width, int height, int fps);
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
    std::chrono::steady_clock::time_point start_time_;
    std::atomic<int> frame_count_{0};

    // FFmpeg объекты (RAII)
    AVFormatContext* input_ctx_ = nullptr;
    AVFormatContext* output_ctx_ = nullptr;
    AVCodecContext* dec_ctx_ = nullptr;
    AVCodecContext* enc_ctx_ = nullptr;
    AVFilterGraph* filter_graph_ = nullptr;
    AVFilterContext* buffersrc_ctx_ = nullptr;
    AVFilterContext* buffersink_ctx_ = nullptr;
    AVStream* out_stream_ = nullptr;

    // Вспомогательные
    int video_stream_index_ = -1;
    AVRational input_time_base_ = {1, 1000000}; // для захвата

    // Приватные методы
    bool init_input();
    bool init_output();
    bool init_filters();
    void cleanup();

    // Получить имя устройства захвата в зависимости от платформы
    std::string get_device_name() const;

    // Получить оптимальный кодек
    const AVCodec* get_encoder() const;
};

// -----------------------------------------------------------------------------
// Реализация Recorder
// -----------------------------------------------------------------------------

Recorder::Recorder(const std::string& output_dir, int left, int top, int width, int height, int fps)
    : params_{{output_dir + "/output.mp4"}, left, top, width, height, fps}
{
    // Инициализация FFmpeg (глобальная, однократная)
    static bool initialized = false;
    if (!initialized) {
        avdevice_register_all();
        avformat_network_init();
        initialized = true;
    }
}

Recorder::~Recorder() {
    cleanup();
}

void Recorder::run() {
    if (running_) return;

    // 1. Инициализация
    if (!init_input()) {
        std::cerr << "Ошибка инициализации входа" << std::endl;
        return;
    }
    if (!init_output()) {
        std::cerr << "Ошибка инициализации выхода" << std::endl;
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
    start_time_ = std::chrono::steady_clock::now();
    frame_count_ = 0;

    // 3. Основной цикл
    AVPacket* in_pkt = av_packet_alloc();
    AVFrame* decoded_frame = av_frame_alloc();
    AVFrame* filtered_frame = av_frame_alloc();
    if (!in_pkt || !decoded_frame || !filtered_frame) {
        std::cerr << "Ошибка выделения памяти" << std::endl;
        cleanup();
        return;
    }

    // Таймер для ограничения FPS
    auto next_frame_time = start_time_;

    while (running_) {
        // Читаем пакет из устройства
        int ret = av_read_frame(input_ctx_, in_pkt);
        if (ret < 0) {
            // Если ошибка или конец, ждём немного
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            continue;
        }

        // Проверяем, что это видеопоток
        if (in_pkt->stream_index != video_stream_index_) {
            av_packet_unref(in_pkt);
            continue;
        }

        // Отправляем в декодер
        ret = avcodec_send_packet(dec_ctx_, in_pkt);
        av_packet_unref(in_pkt);
        if (ret < 0) {
            continue;
        }

        // Получаем декодированные кадры
        while (ret >= 0) {
            ret = avcodec_receive_frame(dec_ctx_, decoded_frame);
            if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) {
                break;
            } else if (ret < 0) {
                std::cerr << "Ошибка получения кадра из декодера" << std::endl;
                break;
            }

            // Ограничение FPS: пропускаем кадр, если ещё не пришло время
            auto now = std::chrono::steady_clock::now();
            if (now < next_frame_time) {
                av_frame_unref(decoded_frame);
                continue;
            }
            next_frame_time += std::chrono::milliseconds(1000 / params_.fps);

            // Отправляем кадр в фильтр
            decoded_frame->pts = frame_count_.load();
            if (av_buffersrc_write_frame(buffersrc_ctx_, decoded_frame) < 0) {
                std::cerr << "Ошибка отправки кадра в фильтр" << std::endl;
                av_frame_unref(decoded_frame);
                break;
            }

            // Получаем обработанный кадр из фильтра
            while (true) {
                ret = av_buffersink_get_frame(buffersink_ctx_, filtered_frame);
                if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) {
                    break;
                } else if (ret < 0) {
                    std::cerr << "Ошибка получения кадра из фильтра" << std::endl;
                    break;
                }

                // Кодируем кадр
                filtered_frame->pts = frame_count_.load();
                if (avcodec_send_frame(enc_ctx_, filtered_frame) == 0) {
                    AVPacket* out_pkt = av_packet_alloc();
                    while (avcodec_receive_packet(enc_ctx_, out_pkt) == 0) {
                        av_packet_rescale_ts(out_pkt, enc_ctx_->time_base, out_stream_->time_base);
                        out_pkt->stream_index = out_stream_->index;
                        av_interleaved_write_frame(output_ctx_, out_pkt);
                        av_packet_unref(out_pkt);
                    }
                    av_packet_free(&out_pkt);
                }
                frame_count_++;
                av_frame_unref(filtered_frame);
            }

            av_frame_unref(decoded_frame);
        }
    }

    // 4. Финализация (отправляем пустой кадр в кодировщик)
    avcodec_send_frame(enc_ctx_, nullptr);
    AVPacket* out_pkt = av_packet_alloc();
    while (avcodec_receive_packet(enc_ctx_, out_pkt) == 0) {
        av_packet_rescale_ts(out_pkt, enc_ctx_->time_base, out_stream_->time_base);
        out_pkt->stream_index = out_stream_->index;
        av_interleaved_write_frame(output_ctx_, out_pkt);
        av_packet_unref(out_pkt);
    }
    av_packet_free(&out_pkt);

    // 5. Запись трейлера и закрытие
    av_write_trailer(output_ctx_);

    // 6. Очистка
    av_packet_free(&in_pkt);
    av_frame_free(&decoded_frame);
    av_frame_free(&filtered_frame);
    cleanup();

    std::cout << "Запись завершена. Кадров: " << frame_count_ << std::endl;
}

void Recorder::stop() {
    running_ = false;
}

double Recorder::elapsed_time() const {
    if (!running_) return 0.0;
    auto now = std::chrono::steady_clock::now();
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - start_time_).count();
    return elapsed / 1000.0;
}

int Recorder::frame_count() const {
    return frame_count_.load();
}

// ---------- Инициализация входа ----------
bool Recorder::init_input() {
    std::string device_name = get_device_name();
    if (device_name.empty()) {
        std::cerr << "Не удалось определить устройство захвата" << std::endl;
        return false;
    }

    const AVInputFormat* input_format = av_find_input_format("avfoundation");
#ifdef _WIN32
    input_format = av_find_input_format("dshow");
#elif __linux__
    input_format = av_find_input_format("x11grab");
#endif

    if (!input_format) {
        std::cerr << "Формат ввода не найден" << std::endl;
        return false;
    }

    AVDictionary* opts = nullptr;
    // Устанавливаем частоту кадров для устройства
    std::string fps_str = std::to_string(params_.fps);
    av_dict_set(&opts, "framerate", fps_str.c_str(), 0);
    
    // macOS: avfoundation не поддерживает yuv420p — просим uyvy422
#ifdef __APPLE__
    av_dict_set(&opts, "pixel_format", "uyvy422", 0);
#endif

    // Для x11grab нужны offset_x/y
#ifdef __linux__
    av_dict_set(&opts, "offset_x", std::to_string(params_.left).c_str(), 0);
    av_dict_set(&opts, "offset_y", std::to_string(params_.top).c_str(), 0);
    // Задаём размер захватываемой области (x11grab может захватывать целиком)
    // Здесь мы захватываем весь экран, а обрезку сделаем фильтром
    // Поэтому лучше захватывать весь экран, а параметры left/top использовать в фильтре
    // Поэтому игнорируем offset и захватываем весь экран.
    // Для этого передадим имя устройства как ":0.0" (или аналогично)
    // Но проще захватывать весь экран с помощью x11grab без смещения.
    // Мы передадим координаты в фильтр crop.
    device_name = ":0.0"; // можно также получить из DISPLAY
#endif

    int ret = avformat_open_input(&input_ctx_, device_name.c_str(), input_format, &opts);
    av_dict_free(&opts);
    if (ret < 0) {
        std::cerr << "Ошибка открытия устройства захвата: " << ret << std::endl;
        return false;
    }

    if (avformat_find_stream_info(input_ctx_, nullptr) < 0) {
        std::cerr << "Не удалось получить информацию о потоках" << std::endl;
        return false;
    }

    // Найти видеопоток
    for (unsigned i = 0; i < input_ctx_->nb_streams; i++) {
        if (input_ctx_->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
            video_stream_index_ = i;
            break;
        }
    }
    if (video_stream_index_ == -1) {
        std::cerr << "Видеопоток не найден" << std::endl;
        return false;
    }

    // Декодер
    AVCodecParameters* codecpar = input_ctx_->streams[video_stream_index_]->codecpar;
    const AVCodec* dec = avcodec_find_decoder(codecpar->codec_id);
    if (!dec) {
        std::cerr << "Декодер не найден" << std::endl;
        return false;
    }

    dec_ctx_ = avcodec_alloc_context3(dec);
    if (!dec_ctx_) {
        std::cerr << "Не удалось выделить контекст декодера" << std::endl;
        return false;
    }
    if (avcodec_parameters_to_context(dec_ctx_, codecpar) < 0) {
        std::cerr << "Ошибка копирования параметров в декодер" << std::endl;
        return false;
    }
    if (avcodec_open2(dec_ctx_, dec, nullptr) < 0) {
        std::cerr << "Ошибка открытия декодера" << std::endl;
        return false;
    }

    input_time_base_ = input_ctx_->streams[video_stream_index_]->time_base;
    return true;
}


// ---------- Инициализация выхода ----------
bool Recorder::init_output() {
    // Создаём выходной контекст
    int ret = avformat_alloc_output_context2(&output_ctx_, nullptr, "mp4", params_.output_path.c_str());
    if (ret < 0 || !output_ctx_) {
        std::cerr << "Ошибка создания выходного контекста" << std::endl;
        return false;
    }

    const AVCodec* enc = get_encoder();
    if (!enc) {
        std::cerr << "Кодек не найден" << std::endl;
        return false;
    }

    out_stream_ = avformat_new_stream(output_ctx_, enc);
    if (!out_stream_) {
        std::cerr << "Ошибка создания выходного потока" << std::endl;
        return false;
    }

    enc_ctx_ = avcodec_alloc_context3(enc);
    if (!enc_ctx_) {
        std::cerr << "Ошибка выделения контекста кодера" << std::endl;
        return false;
    }

    // Настройка кодера
    enc_ctx_->codec_type = AVMEDIA_TYPE_VIDEO;
    enc_ctx_->width = params_.width;
    enc_ctx_->height = params_.height;
    enc_ctx_->time_base = AVRational{1, params_.fps};
    enc_ctx_->framerate = AVRational{params_.fps, 1};
    enc_ctx_->pix_fmt = AV_PIX_FMT_YUV420P; // общий формат

    // Настройки качества в зависимости от кодека
    if (enc->id == AV_CODEC_ID_H264) {
        // Если видеотулбокс
        if (strcmp(enc->name, "h264_videotoolbox") == 0) {
            av_opt_set(enc_ctx_->priv_data, "bitrate", std::to_string(params_.bitrate_kbps * 1000).c_str(), 0);
            av_opt_set(enc_ctx_->priv_data, "quality", std::to_string(params_.quality).c_str(), 0);
            av_opt_set(enc_ctx_->priv_data, "allow_sw", "1", 0); // разрешить программный, если аппаратный недоступен
        } else {
            av_opt_set(enc_ctx_->priv_data, "preset", "medium", 0);
            av_opt_set(enc_ctx_->priv_data, "crf", "23", 0);
        }
    }

    // Открыть кодер
    if (avcodec_open2(enc_ctx_, enc, nullptr) < 0) {
        std::cerr << "Ошибка открытия кодера" << std::endl;
        return false;
    }

    // Копировать параметры в поток
    avcodec_parameters_from_context(out_stream_->codecpar, enc_ctx_);
    out_stream_->time_base = enc_ctx_->time_base;

    // Открыть файл
    if (!(output_ctx_->oformat->flags & AVFMT_NOFILE)) {
        if (avio_open(&output_ctx_->pb, params_.output_path.c_str(), AVIO_FLAG_WRITE) < 0) {
            std::cerr << "Ошибка открытия выходного файла" << std::endl;
            return false;
        }
    }

    // Записать заголовок
    if (avformat_write_header(output_ctx_, nullptr) < 0) {
        std::cerr << "Ошибка записи заголовка" << std::endl;
        return false;
    }

    return true;
}

// ---------- Инициализация фильтров ----------
bool Recorder::init_filters() {
    filter_graph_ = avfilter_graph_alloc();
    if (!filter_graph_) {
        std::cerr << "Ошибка выделения графа фильтров" << std::endl;
        return false;
    }

    // Источник (buffer)
    const AVFilter* buffersrc = avfilter_get_by_name("buffer");
    const AVFilter* buffersink = avfilter_get_by_name("buffersink");

    // Параметры источника (входной формат из декодера)
    char args[512];
    snprintf(args, sizeof(args),
        "video_size=%dx%d:pix_fmt=%d:time_base=%d/%d:pixel_aspect=1/1",
        dec_ctx_->width, dec_ctx_->height, dec_ctx_->pix_fmt,
        input_time_base_.num, input_time_base_.den);

    if (avfilter_graph_create_filter(&buffersrc_ctx_, buffersrc, "in", args, nullptr, filter_graph_) < 0) {
        std::cerr << "Ошибка создания фильтра-источника" << std::endl;
        return false;
    }

    // Приёмник (buffersink) – будет принимать yuv420p
    if (avfilter_graph_create_filter(&buffersink_ctx_, buffersink, "out", nullptr, nullptr, filter_graph_) < 0) {
        std::cerr << "Ошибка создания фильтра-приёмника" << std::endl;
        return false;
    }

    // Устанавливаем список форматов для buffersink через опцию (до конфигурации)
    enum AVPixelFormat pix_fmts[] = { AV_PIX_FMT_YUV420P, AV_PIX_FMT_NONE };
    av_opt_set_bin(buffersink_ctx_, "pix_fmts", (const uint8_t*)pix_fmts,
                   sizeof(pix_fmts) - sizeof(pix_fmts[0]), AV_OPT_SEARCH_CHILDREN);

    // Строим цепочку фильтров: crop + формат yuv420p
    int crop_left = params_.left;
    int crop_top = params_.top;
    // Убедимся, что координаты и размеры чётные (для безопасности)
    if (crop_left % 2 != 0) crop_left--;
    if (crop_top % 2 != 0) crop_top--;
    int crop_w = params_.width;
    int crop_h = params_.height;
    if (crop_w % 2 != 0) crop_w--;
    if (crop_h % 2 != 0) crop_h--;
    // Проверяем, что не выходим за границы
    if (crop_left + crop_w > dec_ctx_->width) crop_w = dec_ctx_->width - crop_left;
    if (crop_top + crop_h > dec_ctx_->height) crop_h = dec_ctx_->height - crop_top;

    char filter_desc[512];
    snprintf(filter_desc, sizeof(filter_desc),
        "crop=%d:%d:%d:%d,format=yuv420p",
        crop_w, crop_h, crop_left, crop_top);

    // Соединяем через avfilter_graph_parse_ptr
    AVFilterInOut* outputs = avfilter_inout_alloc();
    AVFilterInOut* inputs = avfilter_inout_alloc();
    outputs->name = av_strdup("in");
    outputs->filter_ctx = buffersrc_ctx_;
    outputs->pad_idx = 0;
    outputs->next = nullptr;

    inputs->name = av_strdup("out");
    inputs->filter_ctx = buffersink_ctx_;
    inputs->pad_idx = 0;
    inputs->next = nullptr;

    if (avfilter_graph_parse_ptr(filter_graph_, filter_desc, &inputs, &outputs, nullptr) < 0) {
        std::cerr << "Ошибка разбора цепочки фильтров" << std::endl;
        avfilter_inout_free(&outputs);
        avfilter_inout_free(&inputs);
        return false;
    }
    avfilter_inout_free(&outputs);
    avfilter_inout_free(&inputs);

    if (avfilter_graph_config(filter_graph_, nullptr) < 0) {
        std::cerr << "Ошибка конфигурации графа фильтров" << std::endl;
        return false;
    }

    return true;
}

// ---------- Очистка ресурсов ----------
void Recorder::cleanup() {
    if (input_ctx_) {
        avformat_close_input(&input_ctx_);
        input_ctx_ = nullptr;
    }
    if (output_ctx_) {
        if (output_ctx_->pb) {
            avio_closep(&output_ctx_->pb);
        }
        avformat_free_context(output_ctx_);
        output_ctx_ = nullptr;
    }
    if (dec_ctx_) {
        avcodec_free_context(&dec_ctx_);
        dec_ctx_ = nullptr;
    }
    if (enc_ctx_) {
        avcodec_free_context(&enc_ctx_);
        enc_ctx_ = nullptr;
    }
    if (filter_graph_) {
        avfilter_graph_free(&filter_graph_);
        filter_graph_ = nullptr;
        buffersrc_ctx_ = nullptr;
        buffersink_ctx_ = nullptr;
    }
    out_stream_ = nullptr;
    video_stream_index_ = -1;
}

// ---------- Определение устройства ----------
std::string Recorder::get_device_name() const {
#ifdef __APPLE__
    // На macOS используем avfoundation: обычно экран имеет индекс 1 или 0
    // Попробуем перебор
    const char* devices[] = {"1", "0", "2", "3"};
    for (const char* dev : devices) {
        // Проверяем, открывается ли устройство
        AVFormatContext* test_ctx = nullptr;
        const AVInputFormat* fmt = av_find_input_format("avfoundation");
        if (fmt && avformat_open_input(&test_ctx, dev, fmt, nullptr) == 0) {
            avformat_close_input(&test_ctx);
            return dev;
        }
    }
    return "1"; // fallback
#elif _WIN32
    // Windows: используем dshow, обычно "video=screen-capture-recorder" или аналоги
    // Можно попробовать "video=UScreenCapture" или "video=screen-capture-recorder"
    return "video=screen-capture-recorder";
#elif __linux__
    // Linux: X11 grab, передаём :0.0
    return ":0.0";
#else
    return "";
#endif
}

// ---------- Выбор кодера ----------
const AVCodec* Recorder::get_encoder() const {
    // Сначала пробуем аппаратный
    const AVCodec* enc = avcodec_find_encoder_by_name("h264_videotoolbox");
#ifdef _WIN32
    enc = avcodec_find_encoder_by_name("h264_nvenc");
    if (!enc) enc = avcodec_find_encoder_by_name("h264_amf");
#endif
#ifdef __linux__
    enc = avcodec_find_encoder_by_name("h264_nvenc"); // если есть NVIDIA
    if (!enc) enc = avcodec_find_encoder_by_name("h264_vaapi");
#endif
    if (!enc) {
        // Fallback на libx264
        enc = avcodec_find_encoder(AV_CODEC_ID_H264);
    }
    return enc;
}

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

int recorder_start(const char* output_dir, int left, int top, int width, int height, int fps) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (g_recorder && g_recorder->is_running()) {
        std::cerr << "Запись уже запущена" << std::endl;
        return -1;
    }

    // Создаём объект Recorder
    g_recorder = std::make_unique<Recorder>(output_dir, left, top, width, height, fps);

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