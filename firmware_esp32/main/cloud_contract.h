#pragma once

#include <stddef.h>
#include <stdint.h>
#include "device_config.h"
#include "fusion.h"
#include "camera_scores_protocol.h"

#define SG_CLOUD_UPLINK_MAX  1536
#define SG_DOWNLINK_MAX       768
#define SG_ADVICE_TEXT_MAX    384
#define SG_ADVICE_SOURCE_MAX   64

typedef enum {
    SG_CONTRACT_OK = 0,
    SG_CONTRACT_INVALID_JSON = -1,
    SG_CONTRACT_INVALID_FIELD = -2,
    SG_CONTRACT_TOO_LARGE = -3,
} sg_contract_err_t;

typedef struct {
    sg_level_t level;
    int64_t ts;
    char advice_text[SG_ADVICE_TEXT_MAX + 1];
    char source[SG_ADVICE_SOURCE_MAX + 1];
} sg_cloud_advice_t;

typedef struct {
    sg_screening_control_t action;
} sg_cloud_screening_control_t;

int sg_cloud_build_uplink(char *buf, size_t cap,
                          const sg_device_config_t *cfg,
                          const sg_scores_in_t *scores,
                          const sg_fusion_out_t *fusion,
                          sg_screening_stage_t screening_stage,
                          int64_t unix_ts, uint32_t seq);

sg_contract_err_t sg_cloud_parse_advice(const char *json, size_t len,
                                        sg_cloud_advice_t *out);
sg_contract_err_t sg_cloud_parse_screening_control(
    const char *json, size_t len, sg_cloud_screening_control_t *out);
