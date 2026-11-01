// cpp/recorder.h
#ifndef RECORDER_H
#define RECORDER_H

#include "pik2video/params.h"

#ifdef __cplusplus
extern "C" {
#endif

int  recorder_start(const Pik2VideoParams* params);
void recorder_stop();
double recorder_get_elapsed_time();
int  recorder_get_frame_count();

#ifdef __cplusplus
}
#endif

#endif // RECORDER_H
