#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SG_SPEECH_FRAME_SAMPLES 320
#define SG_SPEECH_MAX_FRAMES 200
#define SG_SPEECH_NOISE_FRAMES 15

typedef enum {
    SG_SPEECH_IDLE = 0,
    SG_SPEECH_LISTENING,
    SG_SPEECH_COMPLETE,
    SG_SPEECH_RETRY,
} sg_speech_state_t;

typedef enum {
    SG_SPEECH_REASON_NONE = 0,
    SG_SPEECH_REASON_NO_VOICE,
    SG_SPEECH_REASON_TOO_SHORT,
    SG_SPEECH_REASON_TOO_QUIET,
    SG_SPEECH_REASON_CLIPPED,
    SG_SPEECH_REASON_IO_ERROR,
    SG_SPEECH_REASON_NON_SPEECH,
} sg_speech_reason_t;

typedef struct {
    uint32_t window_id;
    sg_speech_state_t state;
    bool available;
    uint8_t score;
    float p_clear;
    sg_speech_reason_t reason;
    uint16_t valid_frames;
    uint16_t voiced_frames;
    float rms;
    int16_t peak;
} sg_speech_result_t;

typedef struct {
    sg_speech_result_t result;
    float noise_rms_sum;
    float noise_rms;
    double voiced_rms_sum;
    double voiced_rms_sq_sum;
    double zcr_sum;
    double band_sum[3];
    uint32_t clipped_samples;
    uint32_t total_samples;
    uint16_t current_voice_run;
    uint16_t longest_voice_run;
} sg_speech_context_t;

void sg_speech_screening_init(sg_speech_context_t *context);
void sg_speech_screening_start(sg_speech_context_t *context);
void sg_speech_screening_cancel(sg_speech_context_t *context);
void sg_speech_screening_process(sg_speech_context_t *context,
                                 const int16_t *samples, size_t count);
void sg_speech_screening_fail(sg_speech_context_t *context,
                              sg_speech_reason_t reason);
void sg_speech_screening_snapshot(const sg_speech_context_t *context,
                                  sg_speech_result_t *result);
