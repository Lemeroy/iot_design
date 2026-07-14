#pragma once

#include <stdint.h>

#define SG_CAMERA_PROTOCOL_V1 1U
#define SG_CAMERA_I2C_ADDRESS 0x42U

enum {
    SG_CAMERA_VALID_FACE = 1U << 0,
    SG_CAMERA_VALID_TONGUE = 1U << 1,
    SG_CAMERA_VALID_EYE = 1U << 2,
    SG_CAMERA_VALID_ALL = SG_CAMERA_VALID_FACE
                        | SG_CAMERA_VALID_TONGUE
                        | SG_CAMERA_VALID_EYE,
};

typedef enum {
    SG_CAMERA_STATUS_READY = 0,
    SG_CAMERA_STATUS_BUSY = 1,
    SG_CAMERA_STATUS_NO_FACE = 2,
    SG_CAMERA_STATUS_MODEL_MISSING = 3,
    SG_CAMERA_STATUS_ERROR = 4,
} sg_camera_status_t;

typedef enum {
    SG_CAMERA_PROTOCOL_OK = 0,
    SG_CAMERA_PROTOCOL_BAD_VERSION,
    SG_CAMERA_PROTOCOL_BAD_CRC,
    SG_CAMERA_PROTOCOL_BAD_VALUE,
} sg_camera_protocol_result_t;

typedef struct __attribute__((packed)) {
    uint8_t version;
    uint8_t sequence;
    uint8_t face;
    uint8_t tongue;
    uint8_t eye;
    uint8_t quality;
    uint8_t valid_mask;
    uint8_t status;
    int16_t mouth_angle_x10;
    uint16_t latency_ms;
    uint16_t crc16;
} sg_camera_scores_v1_t;

_Static_assert(sizeof(sg_camera_scores_v1_t) == 14,
               "camera score protocol v1 must be 14 bytes");

uint16_t sg_camera_scores_crc(const sg_camera_scores_v1_t *frame);

sg_camera_protocol_result_t sg_camera_scores_validate(
    const sg_camera_scores_v1_t *frame);
