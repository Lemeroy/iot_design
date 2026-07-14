#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "unity.h"
#include "unity_test_runner.h"

#include "camera_scores_protocol.h"

static sg_camera_scores_v1_t valid_frame(void)
{
    sg_camera_scores_v1_t frame = {
        .version = SG_CAMERA_PROTOCOL_V1,
        .sequence = 7,
        .face = 81,
        .tongue = 72,
        .eye = 90,
        .quality = 88,
        .valid_mask = SG_CAMERA_VALID_FACE | SG_CAMERA_VALID_EYE,
        .status = SG_CAMERA_STATUS_READY,
        .mouth_angle_x10 = 35,
        .latency_ms = 42,
    };
    frame.crc16 = sg_camera_scores_crc(&frame);
    return frame;
}

TEST_CASE("camera score v1 validates known frame", "[camera_protocol]")
{
    sg_camera_scores_v1_t frame = valid_frame();
    TEST_ASSERT_EQUAL_UINT32(14, sizeof(frame));
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_OK,
                      sg_camera_scores_validate(&frame));
}

TEST_CASE("camera score rejects corrupt CRC", "[camera_protocol]")
{
    sg_camera_scores_v1_t frame = valid_frame();
    frame.quality ^= 1U;
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_CRC,
                      sg_camera_scores_validate(&frame));
}

TEST_CASE("camera score rejects unsupported version", "[camera_protocol]")
{
    sg_camera_scores_v1_t frame = valid_frame();
    frame.version = 2;
    frame.crc16 = sg_camera_scores_crc(&frame);
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VERSION,
                      sg_camera_scores_validate(&frame));
}

TEST_CASE("camera score rejects valid modality above 100", "[camera_protocol]")
{
    sg_camera_scores_v1_t frame = valid_frame();
    frame.face = 101;
    frame.crc16 = sg_camera_scores_crc(&frame);
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VALUE,
                      sg_camera_scores_validate(&frame));
}

TEST_CASE("camera score ignores value when modality is invalid", "[camera_protocol]")
{
    sg_camera_scores_v1_t frame = valid_frame();
    frame.tongue = 255;
    frame.crc16 = sg_camera_scores_crc(&frame);
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_OK,
                      sg_camera_scores_validate(&frame));
}

TEST_CASE("camera score rejects unknown status and validity bits", "[camera_protocol]")
{
    sg_camera_scores_v1_t frame = valid_frame();
    frame.status = 255;
    frame.crc16 = sg_camera_scores_crc(&frame);
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VALUE,
                      sg_camera_scores_validate(&frame));

    frame = valid_frame();
    frame.valid_mask = 0x80;
    frame.crc16 = sg_camera_scores_crc(&frame);
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VALUE,
                      sg_camera_scores_validate(&frame));
}

void app_main(void)
{
    unity_run_all_tests();
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
