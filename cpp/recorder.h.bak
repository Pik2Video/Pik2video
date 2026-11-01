// cpp/recorder.h
#ifndef RECORDER_H
#define RECORDER_H

#ifdef __cplusplus
extern "C" {
#endif

// Функции, вызываемые из Python (через ctypes)
int  recorder_start(const char* output_dir, int left, int top, int width, int height, int fps);
void recorder_stop();
double recorder_get_elapsed_time();
int  recorder_get_frame_count();

#ifdef __cplusplus
}
#endif

#endif // RECORDER_H