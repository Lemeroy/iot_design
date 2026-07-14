#include "camera_scores_protocol.h"

#include <string.h>

sg_camera_protocol_result_t sg_camera_face_bbox_parse(
    const uint8_t *raw, size_t length, sg_camera_face_bbox_t *out)
{
    if (raw == NULL || out == NULL || length != sizeof(sg_camera_face_response_t)) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }

    const sg_camera_face_response_t *wire =
        (const sg_camera_face_response_t *)raw;
    memset(out, 0, sizeof(*out));
    out->center_x = wire->center_x;
    out->center_y = wire->center_y;
    out->width = wire->width;
    out->height = wire->height;
    out->valid = wire->center_x != 0U || wire->center_y != 0U
              || wire->width != 0U || wire->height != 0U;
    return SG_CAMERA_PROTOCOL_OK;
}

void sg_camera_face_response_encode(
    const sg_camera_face_bbox_t *bbox, sg_camera_face_response_t *out)
{
    if (out == NULL) {
        return;
    }
    memset(out, 0, sizeof(*out));
    if (bbox == NULL || !bbox->valid) {
        return;
    }
    out->center_x = bbox->center_x;
    out->center_y = bbox->center_y;
    out->width = bbox->width;
    out->height = bbox->height;
}
