#include "camera_scores_protocol.h"

#include <stddef.h>

static uint16_t crc16_ccitt_false(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFFU;
    for (size_t i = 0; i < length; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (uint8_t bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x8000U) != 0U
                ? (uint16_t)((crc << 1) ^ 0x1021U)
                : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

uint16_t sg_camera_scores_crc(const sg_camera_scores_v1_t *frame)
{
    if (frame == NULL) {
        return 0U;
    }
    return crc16_ccitt_false((const uint8_t *)frame,
                             offsetof(sg_camera_scores_v1_t, crc16));
}

sg_camera_protocol_result_t sg_camera_scores_validate(
    const sg_camera_scores_v1_t *frame)
{
    if (frame == NULL) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }
    if (frame->version != SG_CAMERA_PROTOCOL_V1) {
        return SG_CAMERA_PROTOCOL_BAD_VERSION;
    }
    if (frame->crc16 != sg_camera_scores_crc(frame)) {
        return SG_CAMERA_PROTOCOL_BAD_CRC;
    }
    if ((frame->valid_mask & (uint8_t)~SG_CAMERA_VALID_ALL) != 0U
        || frame->status > SG_CAMERA_STATUS_ERROR
        || frame->quality > 100U) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }
    if (((frame->valid_mask & SG_CAMERA_VALID_FACE) != 0U
         && frame->face > 100U)
        || ((frame->valid_mask & SG_CAMERA_VALID_TONGUE) != 0U
            && frame->tongue > 100U)
        || ((frame->valid_mask & SG_CAMERA_VALID_EYE) != 0U
            && frame->eye > 100U)) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }
    return SG_CAMERA_PROTOCOL_OK;
}
