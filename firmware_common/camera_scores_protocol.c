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

sg_camera_protocol_result_t sg_camera_face_metrics_parse(
    const uint8_t *raw, size_t length, sg_camera_face_metrics_t *out)
{
    if (raw == NULL || out == NULL
        || length != sizeof(sg_camera_face_metrics_response_t)) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }

    const sg_camera_face_metrics_response_t *wire =
        (const sg_camera_face_metrics_response_t *)raw;
    if (wire->status > 1U) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }

    memset(out, 0, sizeof(*out));
    if (wire->status == 0U) {
        return SG_CAMERA_PROTOCOL_OK;
    }
    if (wire->score > 100U || wire->quality > 100U
        || wire->mouth_angle_deg < -90 || wire->mouth_angle_deg > 90) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }

    out->valid = true;
    out->score = wire->score;
    out->mouth_angle_deg = wire->mouth_angle_deg;
    out->quality = wire->quality;
    return SG_CAMERA_PROTOCOL_OK;
}

void sg_camera_face_metrics_encode(
    const sg_camera_face_metrics_t *metrics,
    sg_camera_face_metrics_response_t *out)
{
    if (out == NULL) {
        return;
    }
    memset(out, 0, sizeof(*out));
    if (metrics == NULL || !metrics->valid || metrics->score > 100U
        || metrics->quality > 100U || metrics->mouth_angle_deg < -90
        || metrics->mouth_angle_deg > 90) {
        return;
    }
    out->status = 1U;
    out->score = metrics->score;
    out->mouth_angle_deg = metrics->mouth_angle_deg;
    out->quality = metrics->quality;
}

sg_camera_protocol_result_t sg_camera_modal_parse(
    const uint8_t *raw, size_t length, sg_camera_modal_metrics_t *out)
{
    if (raw == NULL || out == NULL
        || length != sizeof(sg_camera_modal_response_t)) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }
    if (raw[0] > 1U) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }

    memset(out, 0, sizeof(*out));
    if (raw[0] == 0U) {
        return SG_CAMERA_PROTOCOL_OK;
    }
    const int8_t signed_value = (int8_t)raw[2];
    if (raw[1] > 100U || raw[3] > 100U
        || signed_value < -100 || signed_value > 100) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }
    out->valid = true;
    out->score = raw[1];
    out->signed_value = signed_value;
    out->quality = raw[3];
    return SG_CAMERA_PROTOCOL_OK;
}

void sg_camera_modal_encode(
    const sg_camera_modal_metrics_t *metrics,
    sg_camera_modal_response_t *out)
{
    if (out == NULL) {
        return;
    }
    memset(out, 0, sizeof(*out));
    if (metrics == NULL || !metrics->valid || metrics->score > 100U
        || metrics->quality > 100U || metrics->signed_value < -100
        || metrics->signed_value > 100) {
        return;
    }
    uint8_t *raw = (uint8_t *)out;
    raw[0] = 1U;
    raw[1] = metrics->score;
    raw[2] = (uint8_t)metrics->signed_value;
    raw[3] = metrics->quality;
}

sg_camera_protocol_result_t sg_camera_stage_parse(
    const uint8_t *raw, size_t length, sg_camera_stage_status_t *out)
{
    if (raw == NULL || out == NULL
        || length != sizeof(sg_camera_stage_response_t)
        || raw[0] > SG_STAGE_ERROR || raw[1] > 100U
        || raw[2] != 0U || raw[3] != 0U) {
        return SG_CAMERA_PROTOCOL_BAD_VALUE;
    }
    out->stage = (sg_screening_stage_t)raw[0];
    out->progress = raw[1];
    return SG_CAMERA_PROTOCOL_OK;
}

void sg_camera_stage_encode(
    const sg_camera_stage_status_t *status,
    sg_camera_stage_response_t *out)
{
    if (out == NULL) {
        return;
    }
    memset(out, 0, sizeof(*out));
    if (status == NULL || status->stage > SG_STAGE_ERROR
        || status->progress > 100U) {
        return;
    }
    uint8_t *raw = (uint8_t *)out;
    raw[0] = (uint8_t)status->stage;
    raw[1] = status->progress;
}
