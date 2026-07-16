#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SG_CAMERA_I2C_ADDRESS 0x52U
#define SG_CAMERA_FACE_REGISTER 0x01U
#define SG_CAMERA_FACE_METRICS_REGISTER 0x02U
#define SG_CAMERA_EYE_REGISTER 0x03U
#define SG_CAMERA_TONGUE_REGISTER 0x04U
#define SG_CAMERA_CONTROL_REGISTER 0x10U
#define SG_CAMERA_STAGE_REGISTER 0x11U

typedef enum {
    SG_CAMERA_PROTOCOL_OK = 0,
    SG_CAMERA_PROTOCOL_BAD_VALUE,
} sg_camera_protocol_result_t;

typedef struct __attribute__((packed)) {
    uint8_t center_x;
    uint8_t center_y;
    uint8_t width;
    uint8_t height;
} sg_camera_face_response_t;

typedef struct __attribute__((packed)) {
    uint8_t status;
    uint8_t score;
    int8_t mouth_angle_deg;
    uint8_t quality;
} sg_camera_face_metrics_response_t;

typedef struct __attribute__((packed)) {
    uint8_t status;
    uint8_t score;
    int8_t signed_value;
    uint8_t quality;
} sg_camera_modal_response_t;

typedef enum {
    SG_SCREENING_CANCEL = 0,
    SG_SCREENING_START = 1,
} sg_screening_control_t;

typedef enum {
    SG_STAGE_IDLE = 0,
    SG_STAGE_FACE = 1,
    SG_STAGE_EYE_CENTER = 2,
    SG_STAGE_EYE_LEFT = 3,
    SG_STAGE_EYE_RIGHT = 4,
    SG_STAGE_TONGUE = 5,
    SG_STAGE_DONE = 6,
    SG_STAGE_ERROR = 7,
} sg_screening_stage_t;

typedef struct __attribute__((packed)) {
    uint8_t stage;
    uint8_t progress;
    uint8_t reserved0;
    uint8_t reserved1;
} sg_camera_stage_response_t;

#ifdef __cplusplus
static_assert(sizeof(sg_camera_face_response_t) == 4,
              "vendor face response must be 4 bytes");
static_assert(sizeof(sg_camera_face_metrics_response_t) == 4,
              "face metrics response must be 4 bytes");
static_assert(sizeof(sg_camera_modal_response_t) == 4,
              "modal response must be 4 bytes");
static_assert(sizeof(sg_camera_stage_response_t) == 4,
              "stage response must be 4 bytes");
#else
_Static_assert(sizeof(sg_camera_face_response_t) == 4,
               "vendor face response must be 4 bytes");
_Static_assert(sizeof(sg_camera_face_metrics_response_t) == 4,
               "face metrics response must be 4 bytes");
_Static_assert(sizeof(sg_camera_modal_response_t) == 4,
               "modal response must be 4 bytes");
_Static_assert(sizeof(sg_camera_stage_response_t) == 4,
               "stage response must be 4 bytes");
#endif

typedef struct {
    bool valid;
    uint8_t center_x;
    uint8_t center_y;
    uint8_t width;
    uint8_t height;
} sg_camera_face_bbox_t;

typedef struct {
    bool valid;
    uint8_t score;
    int8_t mouth_angle_deg;
    uint8_t quality;
} sg_camera_face_metrics_t;

typedef struct {
    bool valid;
    uint8_t score;
    int8_t signed_value;
    uint8_t quality;
} sg_camera_modal_metrics_t;

typedef struct {
    sg_screening_stage_t stage;
    uint8_t progress;
} sg_camera_stage_status_t;

sg_camera_protocol_result_t sg_camera_face_bbox_parse(
    const uint8_t *raw, size_t length, sg_camera_face_bbox_t *out);

void sg_camera_face_response_encode(
    const sg_camera_face_bbox_t *bbox, sg_camera_face_response_t *out);

sg_camera_protocol_result_t sg_camera_face_metrics_parse(
    const uint8_t *raw, size_t length, sg_camera_face_metrics_t *out);

void sg_camera_face_metrics_encode(
    const sg_camera_face_metrics_t *metrics,
    sg_camera_face_metrics_response_t *out);

sg_camera_protocol_result_t sg_camera_modal_parse(
    const uint8_t *raw, size_t length, sg_camera_modal_metrics_t *out);

void sg_camera_modal_encode(
    const sg_camera_modal_metrics_t *metrics,
    sg_camera_modal_response_t *out);

sg_camera_protocol_result_t sg_camera_stage_parse(
    const uint8_t *raw, size_t length, sg_camera_stage_status_t *out);

void sg_camera_stage_encode(
    const sg_camera_stage_status_t *status,
    sg_camera_stage_response_t *out);

#ifdef __cplusplus
}
#endif
