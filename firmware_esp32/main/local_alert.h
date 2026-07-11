#pragma once

#include "esp_err.h"
#include "cloud_contract.h"
#include "fusion.h"

esp_err_t sg_local_alert_init(void);
void sg_local_alert_apply_fusion(const sg_fusion_out_t *fusion);
void sg_local_alert_apply_advice(const sg_cloud_advice_t *advice);
sg_level_t sg_local_alert_get_level(void);
