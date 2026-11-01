// cpp/include/pik2video/params.h
#ifndef PIK2VIDEO_PARAMS_H
#define PIK2VIDEO_PARAMS_H

#ifdef __cplusplus
extern "C" {
#endif

// Параметры записи. Расширяемо без изменения C API.
typedef struct {
    const char* output_dir;    // каталог для output.mp4
    int left, top;             // координаты захвата на экране
    int width, height;         // размеры области захвата
    int fps;                   // целевой FPS
    int bitrate_kbps;          // целевой bitrate, 0 = не использовать (тогда quality)
    int quality;               // 0-100, 0 = не использовать (тогда bitrate)
} Pik2VideoParams;

#ifdef __cplusplus
}
#endif

#endif // PIK2VIDEO_PARAMS_H
