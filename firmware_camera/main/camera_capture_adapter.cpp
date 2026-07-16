#include "camera_capture_adapter.h"
#include "camera_usb_preview.h"

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

static HumanFaceDetect *s_model;
static uint8_t *s_rgb888;

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

static sg_camera_face_bbox_t pick_largest_face(
    const std::list<dl::detect::result_t> &results,
    uint16_t frame_width,
    uint16_t frame_height)
{
    sg_camera_face_bbox_t out = {};
    int best_area = 0;

    for (const auto &result : results) {
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
        out.valid = true;
        out.center_x = scale_to_u8(x0 + w / 2, frame_width);
        out.center_y = scale_to_u8(y0 + h / 2, frame_height);
        out.width = scale_to_u8(w, frame_width);
        out.height = scale_to_u8(h, frame_height);
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
            (void)sg_camera_usb_preview_send(fb, &out->face_bbox);
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
    out->face_bbox = pick_largest_face(results, fb->width, fb->height);

    const long long latency_ms =
        (long long)((esp_timer_get_time() - start_us) / 1000);

    if (sg_camera_usb_preview_requested()) {
        (void)sg_camera_usb_preview_send(fb, &out->face_bbox);
    }

    esp_camera_fb_return(fb);
    if (out->face_bbox.valid) {
        ESP_LOGI(TAG, "face bbox cx=%u cy=%u w=%u h=%u latency=%lldms",
                 out->face_bbox.center_x, out->face_bbox.center_y,
                 out->face_bbox.width, out->face_bbox.height,
                 latency_ms);
    }
    return ESP_OK;
}
