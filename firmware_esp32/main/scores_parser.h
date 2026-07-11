/**
 * @file scores_parser.h
 * @brief 解析 PC -> S3 的 scores JSON 帧
 */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include "fusion.h"

/**
 * @brief 从 UTF-8 JSON payload 解析出 sg_scores_in_t.
 *        允许缺失字段: 缺失的模态分默认 -1, 缺失的 float 字段默认 NaN.
 * @return 0 成功; -1 JSON 语法错; -2 缺少 type 字段或 type 不匹配
 */
int sg_scores_parse(const uint8_t *json, size_t len,
                    sg_scores_in_t *out);
