#pragma once
#include <stdint.h>
#include <stddef.h>

/**
 * @brief CRC16-CCITT (poly=0x1021, init=0xFFFF, no reflect, no xorout)
 */
uint16_t sg_crc16_ccitt(const uint8_t *data, size_t len);

/**
 * @brief 支持流式 update: 传入上一步的 crc 与新数据段
 *        first call: crc = sg_crc16_ccitt(a, la);
 *        next call:  crc = sg_crc16_ccitt_update(crc, b, lb);
 */
uint16_t sg_crc16_ccitt_update(uint16_t crc, const uint8_t *data, size_t len);
