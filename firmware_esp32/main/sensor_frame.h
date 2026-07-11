#pragma once
#include <stddef.h>
#include <stdint.h>

/**
 * @brief Build final M1 frame JSON.
 *
 * Current M1b bring-up mode uses synthetic JPEG/MFCC placeholders because
 * GC2145/INMP441 are not wired yet. The JSON contract is already final:
 * {"type":"frame","jpeg_b64":"...","mfcc":[[...]],"csi_score":0-100}
 *
 * @return payload length, or -1 on overflow/invalid buffer.
 */
int sg_sensor_frame_build_json(char *buf, size_t cap,
                               uint32_t ts, uint32_t seq,
                               int csi_score);
