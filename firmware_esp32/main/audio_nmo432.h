#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "speech_screening.h"

#define SG_NMO432_SAMPLE_RATE 16000
#define SG_NMO432_BLOCK_SAMPLES 320

typedef struct {
    int16_t samples[SG_NMO432_BLOCK_SAMPLES];
    float rms;
    int16_t peak;
    uint16_t clipped_samples;
    bool valid;
} sg_audio_block_t;

esp_err_t sg_audio_nmo432_init(void);
esp_err_t sg_audio_nmo432_read(sg_audio_block_t *out, uint32_t timeout_ms);
esp_err_t sg_audio_nmo432_speech_start(void);
esp_err_t sg_audio_nmo432_speech_cancel(void);
esp_err_t sg_audio_nmo432_speech_snapshot(sg_speech_result_t *result);
