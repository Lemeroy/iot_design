#pragma once
#include <stdint.h>
#include <stddef.h>
#include "fusion.h"

/**
 * @brief 构造 M1a 心跳帧 JSON
 *        {"type":"heartbeat","ts":..,"seq":..,"csi_score":..,"fw":"m1a-0.1"}
 */
int sg_frame_build_heartbeat(char *buf, size_t cap,
                             uint32_t ts, uint32_t seq, int csi_score);

/**
 * @brief 构造融合结果帧 JSON
 *        {"type":"fusion","seq":..,"final":..,"level":"..",
 *         "veto_by":[..], "contributions":{...}, "used_weights":{...},
 *         "reasons":[...]}
 * @return 写入字节数, <=0 出错
 */
int sg_frame_build_fusion(char *buf, size_t cap,
                          const sg_fusion_out_t *out);
