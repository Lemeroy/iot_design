#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "device_config.h"

#define SG_MANAGER_BODY_MAX 1024
#define SG_MANAGER_AUTH_MAX 80
#define SG_MANAGER_RESPONSE_MAX 1536
#define SG_MANAGER_TASK_STACK 12288

typedef enum {
    SG_MANAGER_OK = 0,
    SG_MANAGER_BAD_JSON,
    SG_MANAGER_INVALID_FIELD,
    SG_MANAGER_TOO_LARGE,
} sg_manager_parse_err_t;

sg_manager_parse_err_t sg_manager_parse_profile_patch(
    const char *json, size_t len, uint32_t *expected_revision,
    sg_profile_patch_t *patch);
bool sg_manager_token_equal(const char *expected, const char *provided);
int sg_manager_build_config_json(char *buf, size_t cap,
                                 const sg_device_config_t *cfg);
esp_err_t sg_manager_api_start(void);
