#pragma once

#include "esp_err.h"

esp_err_t sg_audio_out_max98357_init(void);
esp_err_t sg_audio_out_max98357_play_prompt(const char *text);
