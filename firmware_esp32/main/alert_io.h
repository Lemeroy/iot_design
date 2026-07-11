#pragma once

#include "esp_err.h"

esp_err_t sg_alert_io_init(void);
esp_err_t sg_alert_io_set_level(const char *level);
