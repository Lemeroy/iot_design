#pragma once

#include "esp_err.h"

esp_err_t sg_display_st7789_init(void);
esp_err_t sg_display_st7789_show_status(const char *level,
                                        const char *advice_text);
