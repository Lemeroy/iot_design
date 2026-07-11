#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

esp_err_t sg_time_sync_start(void);
bool sg_time_is_synced(void);
int64_t sg_time_unix_seconds(void);
