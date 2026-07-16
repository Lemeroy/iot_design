#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SG_CAMERA_PREVIEW_REQUEST 0xA5U
#define SG_CAMERA_PREVIEW_VERSION 1U
#define SG_CAMERA_PREVIEW_HEADER_SIZE 20U
#define SG_CAMERA_PREVIEW_MAX_JPEG (128U * 1024U)
#define SG_CAMERA_PREVIEW_FLAG_ERROR 0x01U
#define SG_CAMERA_PREVIEW_FLAG_FACE_DETECTED 0x02U
#define SG_CAMERA_PREVIEW_FLAG_LANDMARKS_VALID 0x04U
#define SG_CAMERA_PREVIEW_FLAG_GEOMETRY_VALID 0x08U
#define SG_CAMERA_PREVIEW_FLAG_BASELINE_READY 0x10U
#define SG_CAMERA_PREVIEW_FLAG_F_VALID 0x20U

typedef struct __attribute__((packed)) {
    uint8_t magic[4];
    uint8_t version;
    uint8_t flags;
    uint16_t header_size;
    uint32_t sequence;
    uint32_t jpeg_length;
    uint8_t center_x;
    uint8_t center_y;
    uint8_t width;
    uint8_t height;
} sg_camera_preview_header_t;

void sg_camera_preview_header_init(
    sg_camera_preview_header_t *header,
    uint32_t sequence,
    uint32_t jpeg_length,
    uint8_t flags,
    const uint8_t bbox[4]);

uint32_t sg_camera_preview_crc32(
    uint32_t seed, const void *data, size_t length);

#ifdef __cplusplus
}
#endif
