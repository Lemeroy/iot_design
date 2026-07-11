#pragma once

#include "esp_err.h"

#define SG_MFCC_FRAMES 4
#define SG_MFCC_COEFFS 13

typedef struct {
    float coeffs[SG_MFCC_FRAMES][SG_MFCC_COEFFS];
    int frames;
    int coeffs_per_frame;
} sg_mfcc_frame_t;

esp_err_t sg_audio_inmp441_init(void);
esp_err_t sg_audio_inmp441_read_mfcc(sg_mfcc_frame_t *out);
