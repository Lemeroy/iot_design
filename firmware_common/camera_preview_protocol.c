#include "camera_preview_protocol.h"

#include <string.h>

_Static_assert(
    sizeof(sg_camera_preview_header_t) == SG_CAMERA_PREVIEW_HEADER_SIZE,
    "camera preview header size mismatch");

void sg_camera_preview_header_init(
    sg_camera_preview_header_t *header,
    uint32_t sequence,
    uint32_t jpeg_length,
    uint8_t flags,
    const uint8_t bbox[4])
{
    static const uint8_t magic[4] = {'S', 'G', 'J', 'P'};
    memset(header, 0, sizeof(*header));
    memcpy(header->magic, magic, sizeof(magic));
    header->version = SG_CAMERA_PREVIEW_VERSION;
    header->flags = flags;
    header->header_size = SG_CAMERA_PREVIEW_HEADER_SIZE;
    header->sequence = sequence;
    header->jpeg_length = jpeg_length;
    if (bbox != NULL) {
        header->center_x = bbox[0];
        header->center_y = bbox[1];
        header->width = bbox[2];
        header->height = bbox[3];
    }
}

uint32_t sg_camera_preview_crc32(
    uint32_t seed, const void *data, size_t length)
{
    const uint8_t *bytes = data;
    uint32_t crc = seed ^ 0xFFFFFFFFU;
    for (size_t i = 0; i < length; ++i) {
        crc ^= bytes[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            const uint32_t mask = 0U - (crc & 1U);
            crc = (crc >> 1) ^ (0xEDB88320U & mask);
        }
    }
    return crc ^ 0xFFFFFFFFU;
}
