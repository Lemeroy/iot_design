#include "camera_capture_adapter.h"
#include "camera_usb_preview.h"
#include "face_baseline.h"
#include "face_geometry.h"
#include "eye_tracking.h"
#include "screening_session.h"
#include "tongue_deviation.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <list>
#include <new>

#include "esp_camera.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "human_face_detect.hpp"
#include "img_converters.h"

static const char *TAG = "sg_camera_capture";
static constexpr uint16_t CAMERA_WIDTH = 320;
static constexpr uint16_t CAMERA_HEIGHT = 240;
static constexpr size_t RGB888_BUFFER_SIZE = CAMERA_WIDTH * CAMERA_HEIGHT * 3;
static constexpr uint32_t SG_FACE_REJECT_LOG_INTERVAL = 10;
static constexpr float SG_FACE_PROPOSAL_SCORE_THRESHOLD = 0.40f;
static constexpr float SG_FACE_LANDMARK_SCORE_THRESHOLD = 0.45f;
static constexpr uint8_t SG_FACE_BBOX_HOLD_FRAMES = 2;

static HumanFaceDetect *s_model;
static uint8_t *s_rgb888;
static sg_face_baseline_t s_face_baseline;
static sg_screening_session_t s_screening;
static uint32_t s_face_reject_count;
static const char *s_face_reject_reason;
static sg_camera_face_bbox_t s_last_face_bbox;
static uint8_t s_bbox_miss_count;
static sg_screening_stage_t s_eye_log_stage = SG_STAGE_IDLE;
static uint32_t s_eye_log_count;

static void note_face_rejection(const char *reason)
{
    if (reason == nullptr) {
        s_face_reject_count = 0;
        s_face_reject_reason = nullptr;
        return;
    }
    if (s_face_reject_reason != reason) {
        s_face_reject_reason = reason;
        s_face_reject_count = 0;
    }
    ++s_face_reject_count;
    if (s_face_reject_count == 1
        || s_face_reject_count % SG_FACE_REJECT_LOG_INTERVAL == 0) {
        ESP_LOGI(TAG, "face sample rejected reason=%s count=%lu",
                 reason, (unsigned long)s_face_reject_count);
    }
}

static void bgr888_to_rgb888_in_place(uint8_t *pixels, size_t pixel_count)
{
    for (size_t i = 0; i < pixel_count; ++i) {
        std::swap(pixels[i * 3], pixels[i * 3 + 2]);
    }
}

static uint8_t scale_to_u8(int value, int max_value)
{
    if (max_value <= 0) {
        return 0;
    }
    int scaled = (value * 255 + max_value / 2) / max_value;
    return (uint8_t)std::clamp(scaled, 0, 255);
}

typedef struct {
    sg_camera_face_bbox_t bbox;
    sg_face_geometry_input_t geometry;
    bool landmarks_valid;
} selected_face_t;

static selected_face_t pick_largest_face(
    const std::list<dl::detect::result_t> &results,
    uint16_t frame_width,
    uint16_t frame_height)
{
    selected_face_t out = {};
    int best_area = 0;

    for (const auto &result : results) {
        if (result.box.size() < 4) {
            continue;
        }
        const int x0 = std::clamp((int)std::lround(result.box[0]), 0, (int)frame_width - 1);
        const int y0 = std::clamp((int)std::lround(result.box[1]), 0, (int)frame_height - 1);
        const int x1 = std::clamp((int)std::lround(result.box[2]), 0, (int)frame_width - 1);
        const int y1 = std::clamp((int)std::lround(result.box[3]), 0, (int)frame_height - 1);
        const int w = std::max(0, x1 - x0 + 1);
        const int h = std::max(0, y1 - y0 + 1);
        const int area = w * h;
        if (area <= best_area) {
            continue;
        }

        best_area = area;
        out = {};
        out.bbox.valid = true;
        out.bbox.center_x = scale_to_u8(x0 + w / 2, frame_width);
        out.bbox.center_y = scale_to_u8(y0 + h / 2, frame_height);
        out.bbox.width = scale_to_u8(w, frame_width);
        out.bbox.height = scale_to_u8(h, frame_height);
        if (result.keypoint.size() == 10) {
            out.geometry = {
                .box = {(int16_t)x0, (int16_t)y0, (int16_t)x1, (int16_t)y1},
                .left_eye = {(int16_t)result.keypoint[0], (int16_t)result.keypoint[1]},
                .right_eye = {(int16_t)result.keypoint[6], (int16_t)result.keypoint[7]},
                .nose = {(int16_t)result.keypoint[4], (int16_t)result.keypoint[5]},
                .left_mouth = {(int16_t)result.keypoint[2], (int16_t)result.keypoint[3]},
                .right_mouth = {(int16_t)result.keypoint[8], (int16_t)result.keypoint[9]},
            };
            out.landmarks_valid = true;
        }
    }

    return out;
}

extern "C" esp_err_t sg_camera_capture_init(void)
{
    camera_config_t config = {};
    config.pin_pwdn = -1;
    config.pin_reset = -1;
    config.pin_xclk = 15;
    config.pin_sccb_sda = 4;
    config.pin_sccb_scl = 5;
    config.pin_d7 = 16;
    config.pin_d6 = 17;
    config.pin_d5 = 18;
    config.pin_d4 = 12;
    config.pin_d3 = 10;
    config.pin_d2 = 8;
    config.pin_d1 = 9;
    config.pin_d0 = 11;
    config.pin_vsync = 6;
    config.pin_href = 7;
    config.pin_pclk = 13;
    config.xclk_freq_hz = 15000000;
    config.ledc_timer = LEDC_TIMER_0;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.pixel_format = PIXFORMAT_YUV422;
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_camera_init failed: %s", esp_err_to_name(err));
        return err;
    }
    ESP_ERROR_CHECK_WITHOUT_ABORT(esp_camera_set_psram_mode(true));

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor != nullptr) {
        (void)sensor->set_vflip(sensor, 1);
        (void)sensor->set_hmirror(sensor, 0);
    }

    s_model = new (std::nothrow) HumanFaceDetect(
        static_cast<HumanFaceDetect::model_type_t>(0), false);
    if (s_model == nullptr) {
        ESP_LOGE(TAG, "human face model allocation failed");
        return ESP_ERR_NO_MEM;
    }
    s_model->set_score_thr(SG_FACE_PROPOSAL_SCORE_THRESHOLD, 0);
    s_model->set_score_thr(SG_FACE_LANDMARK_SCORE_THRESHOLD, 1);
    s_rgb888 = static_cast<uint8_t *>(heap_caps_malloc(
        RGB888_BUFFER_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (s_rgb888 == nullptr) {
        ESP_LOGE(TAG, "RGB888 PSRAM buffer allocation failed");
        delete s_model;
        s_model = nullptr;
        return ESP_ERR_NO_MEM;
    }
    ESP_LOGI(TAG, "GC2145 YUV422 + RGB888 human_face_detect ready");
    return ESP_OK;
}

extern "C" esp_err_t sg_camera_capture_control(sg_screening_control_t control)
{
    if (control == SG_SCREENING_START) {
        sg_screening_session_start(&s_screening, esp_timer_get_time());
        ESP_LOGI(TAG, "screening started");
        return ESP_OK;
    }
    if (control == SG_SCREENING_CANCEL) {
        sg_screening_session_cancel(&s_screening);
        ESP_LOGI(TAG, "screening cancelled");
        return ESP_OK;
    }
    return ESP_ERR_INVALID_ARG;
}

extern "C" esp_err_t sg_camera_capture_observe(sg_camera_source_observation_t *out)
{
    if (out == nullptr) {
        return ESP_ERR_INVALID_ARG;
    }
    std::memset(out, 0, sizeof(*out));
    if (s_model == nullptr) {
        return ESP_ERR_INVALID_STATE;
    }

    const int64_t start_us = esp_timer_get_time();
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb == nullptr) {
        return ESP_FAIL;
    }
    if (fb->width != CAMERA_WIDTH || fb->height != CAMERA_HEIGHT ||
        fb->format != PIXFORMAT_YUV422 ||
        !fmt2rgb888(fb->buf, fb->len, fb->format, s_rgb888)) {
        ESP_LOGE(TAG, "YUV422 to RGB888 conversion failed (%ux%u format=%d)",
                 fb->width, fb->height, fb->format);
        if (sg_camera_usb_preview_requested()) {
            (void)sg_camera_usb_preview_send(fb, &out->face_bbox, 0);
        }
        esp_camera_fb_return(fb);
        return ESP_FAIL;
    }
    bgr888_to_rgb888_in_place(s_rgb888, CAMERA_WIDTH * CAMERA_HEIGHT);

    dl::image::img_t img = {
        .data = s_rgb888,
        .width = (uint16_t)fb->width,
        .height = (uint16_t)fb->height,
        .pix_type = dl::image::DL_IMAGE_PIX_TYPE_RGB888,
    };
    auto &results = s_model->run(img);
    const selected_face_t selected =
        pick_largest_face(results, fb->width, fb->height);
    if (selected.bbox.valid) {
        s_last_face_bbox = selected.bbox;
        s_bbox_miss_count = 0;
        out->face_bbox = selected.bbox;
    } else if (s_last_face_bbox.valid
               && s_bbox_miss_count < SG_FACE_BBOX_HOLD_FRAMES) {
        ++s_bbox_miss_count;
        out->face_bbox = s_last_face_bbox;
    } else {
        memset(&s_last_face_bbox, 0, sizeof(s_last_face_bbox));
        s_bbox_miss_count = 0;
    }

    sg_face_frame_metrics_t frame_metrics = {};
    sg_face_frame_metrics_t stable_metrics = {};
    const int64_t now_us = esp_timer_get_time();
    const bool frame_valid = selected.landmarks_valid
        && sg_face_geometry_evaluate(&selected.geometry, &frame_metrics);
    const bool baseline_was_ready = sg_face_baseline_ready(&s_face_baseline);
    if (frame_valid && sg_face_baseline_update(
            &s_face_baseline, &frame_metrics, now_us, &stable_metrics)) {
        out->face_metrics.valid = true;
        out->face_metrics.score = stable_metrics.score;
        out->face_metrics.mouth_angle_deg = static_cast<int8_t>(std::clamp(
            (int)std::lround(stable_metrics.mouth_angle_deg), -90, 90));
        out->face_metrics.quality = stable_metrics.quality;
    } else if (!frame_valid) {
        sg_face_baseline_note_invalid(&s_face_baseline, now_us);
    }
    if (!baseline_was_ready && sg_face_baseline_ready(&s_face_baseline)) {
        ESP_LOGI(TAG, "face baseline ready");
    }

    sg_screening_sample_t screening_sample = {};
    screening_sample.face_ready = frame_valid
        && sg_face_baseline_ready(&s_face_baseline);
    const sg_screening_stage_t stage = sg_screening_session_stage(&s_screening);
    if (stage != s_eye_log_stage) {
        s_eye_log_stage = stage;
        s_eye_log_count = 0;
    }
    if (stage == SG_STAGE_FACE) {
        const char *reason = nullptr;
        if (!selected.bbox.valid) reason = "no_face";
        else if (!selected.landmarks_valid) reason = "landmarks";
        else if (!frame_valid) reason = "geometry";
        else if (!sg_face_baseline_ready(&s_face_baseline)) reason = "baseline";
        note_face_rejection(reason);
        if (reason != nullptr && std::strcmp(reason, "baseline") == 0
            && s_face_reject_count == 1) {
            ESP_LOGI(TAG, "face baseline sample quality=%u count=%u",
                     frame_metrics.quality,
                     (unsigned)s_face_baseline.calibration_count);
        }
    } else {
        note_face_rejection(nullptr);
    }
    if (selected.landmarks_valid
        && (stage == SG_STAGE_EYE_CENTER || stage == SG_STAGE_EYE_LEFT
            || stage == SG_STAGE_EYE_RIGHT)) {
        const int eye_dx = selected.geometry.right_eye.x - selected.geometry.left_eye.x;
        const int eye_dy = selected.geometry.right_eye.y - selected.geometry.left_eye.y;
        const int eye_distance = (int)std::lround(std::hypot(eye_dx, eye_dy));
        const sg_eye_input_t eye_input = {
            .rgb888 = s_rgb888,
            .width = (uint16_t)fb->width,
            .height = (uint16_t)fb->height,
            .stride_bytes = (uint16_t)(fb->width * 3),
            .left_eye = {selected.geometry.left_eye.x, selected.geometry.left_eye.y},
            .right_eye = {selected.geometry.right_eye.x, selected.geometry.right_eye.y},
            .inter_eye_distance = (uint16_t)std::max(0, eye_distance),
            .eye_line_angle_deg = std::atan2((float)eye_dy, (float)eye_dx)
                                * 180.0f / 3.14159265358979323846f,
        };
        screening_sample.eye_valid = sg_eye_measure(
            &eye_input, &screening_sample.eye);
        ++s_eye_log_count;
        if (s_eye_log_count == 1 || s_eye_log_count % 5U == 0) {
            if (screening_sample.eye_valid) {
                ESP_LOGI(TAG,
                         "eye sample stage=%u left=%d right=%d quality=%u",
                         (unsigned)stage, screening_sample.eye.left_x,
                         screening_sample.eye.right_x,
                         screening_sample.eye.quality);
            } else {
                ESP_LOGI(TAG, "eye sample invalid stage=%u count=%lu",
                         (unsigned)stage, (unsigned long)s_eye_log_count);
            }
        }
    } else if (selected.landmarks_valid && stage == SG_STAGE_TONGUE) {
        const int face_width = selected.geometry.box.x1 - selected.geometry.box.x0 + 1;
        const int mouth_y = (selected.geometry.left_mouth.y
                           + selected.geometry.right_mouth.y) / 2;
        const int roi_x = selected.geometry.box.x0 + face_width / 5;
        const int roi_y = std::max(
            (int)selected.geometry.box.y0, mouth_y - face_width / 20);
        const int roi_right = selected.geometry.box.x1 - face_width / 5;
        const int roi_bottom = selected.geometry.box.y1;
        const int eye_dx = selected.geometry.right_eye.x - selected.geometry.left_eye.x;
        const int eye_dy = selected.geometry.right_eye.y - selected.geometry.left_eye.y;
        const sg_tongue_input_t tongue_input = {
            .rgb888 = s_rgb888,
            .width = (uint16_t)fb->width,
            .height = (uint16_t)fb->height,
            .stride_bytes = (uint16_t)(fb->width * 3),
            .roi = {
                (uint16_t)std::max(0, roi_x),
                (uint16_t)std::max(0, roi_y),
                (uint16_t)std::max(0, roi_right - roi_x + 1),
                (uint16_t)std::max(0, roi_bottom - roi_y + 1),
            },
            .axis_origin = {selected.geometry.nose.x, selected.geometry.nose.y},
            .face_width = (uint16_t)std::max(0, face_width),
            .face_roll_deg = std::atan2((float)eye_dy, (float)eye_dx)
                           * 180.0f / 3.14159265358979323846f,
        };
        screening_sample.tongue_valid = sg_tongue_measure(
            &tongue_input, &screening_sample.tongue);
    }
    const sg_screening_stage_t previous_stage = stage;
    sg_screening_session_update(&s_screening, &screening_sample, now_us);
    const sg_screening_stage_t current_stage =
        sg_screening_session_stage(&s_screening);
    if (current_stage != previous_stage) {
        ESP_LOGI(TAG, "screening stage %u -> %u",
                 (unsigned)previous_stage, (unsigned)current_stage);
    }
    (void)sg_screening_session_eye_result(
        &s_screening, &out->eye_metrics);
    (void)sg_screening_session_tongue_result(
        &s_screening, &out->tongue_metrics);
    out->screening.stage = current_stage;
    out->screening.progress = sg_screening_session_progress(
        &s_screening, now_us);

    const long long latency_ms =
        (long long)((esp_timer_get_time() - start_us) / 1000);

    if (sg_camera_usb_preview_requested()) {
        uint8_t preview_flags = 0;
        if (selected.bbox.valid) {
            preview_flags |= SG_CAMERA_PREVIEW_FLAG_FACE_DETECTED;
        }
        if (selected.landmarks_valid) {
            preview_flags |= SG_CAMERA_PREVIEW_FLAG_LANDMARKS_VALID;
        }
        if (frame_valid) {
            preview_flags |= SG_CAMERA_PREVIEW_FLAG_GEOMETRY_VALID;
        }
        if (sg_face_baseline_ready(&s_face_baseline)) {
            preview_flags |= SG_CAMERA_PREVIEW_FLAG_BASELINE_READY;
        }
        if (out->face_metrics.valid) {
            preview_flags |= SG_CAMERA_PREVIEW_FLAG_F_VALID;
        }
        (void)sg_camera_usb_preview_send(
            fb, &out->face_bbox, preview_flags);
    }

    esp_camera_fb_return(fb);
    if (out->face_bbox.valid) {
        ESP_LOGI(TAG, "face bbox cx=%u cy=%u w=%u h=%u latency=%lldms",
                 out->face_bbox.center_x, out->face_bbox.center_y,
                 out->face_bbox.width, out->face_bbox.height,
                 latency_ms);
    }
    if (out->face_metrics.valid) {
        ESP_LOGI(TAG, "face F=%u angle=%d quality=%u latency=%lldms",
                 out->face_metrics.score, out->face_metrics.mouth_angle_deg,
                 out->face_metrics.quality, latency_ms);
    }
    return ESP_OK;
}
