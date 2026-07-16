#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "unity.h"
#include "unity_test_runner.h"

#include "camera_scores_protocol.h"

TEST_CASE("vendor camera protocol uses documented address and face register", "[camera_protocol]")
{
    TEST_ASSERT_EQUAL_UINT8(0x52, SG_CAMERA_I2C_ADDRESS);
    TEST_ASSERT_EQUAL_UINT8(0x01, SG_CAMERA_FACE_REGISTER);
    TEST_ASSERT_EQUAL_UINT8(0x02, SG_CAMERA_FACE_METRICS_REGISTER);
    TEST_ASSERT_EQUAL_UINT32(4, sizeof(sg_camera_face_response_t));
    TEST_ASSERT_EQUAL_UINT32(4, sizeof(sg_camera_face_metrics_response_t));
}

TEST_CASE("face metrics parse a valid signed angle", "[camera_protocol]")
{
    const uint8_t raw[4] = {1, 72, (uint8_t)(int8_t)-8, 91};
    sg_camera_face_metrics_t metrics = {0};
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_OK,
                      sg_camera_face_metrics_parse(raw, sizeof(raw), &metrics));
    TEST_ASSERT_TRUE(metrics.valid);
    TEST_ASSERT_EQUAL_UINT8(72, metrics.score);
    TEST_ASSERT_EQUAL_INT8(-8, metrics.mouth_angle_deg);
    TEST_ASSERT_EQUAL_UINT8(91, metrics.quality);
}

TEST_CASE("face metrics unavailable response clears values", "[camera_protocol]")
{
    const uint8_t raw[4] = {0, 99, 45, 88};
    sg_camera_face_metrics_t metrics = {
        .valid = true,
        .score = 99,
        .mouth_angle_deg = 45,
        .quality = 88,
    };
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_OK,
                      sg_camera_face_metrics_parse(raw, sizeof(raw), &metrics));
    TEST_ASSERT_FALSE(metrics.valid);
    TEST_ASSERT_EQUAL_UINT8(0, metrics.score);
    TEST_ASSERT_EQUAL_INT8(0, metrics.mouth_angle_deg);
    TEST_ASSERT_EQUAL_UINT8(0, metrics.quality);
}

TEST_CASE("face metrics reject malformed values", "[camera_protocol]")
{
    const uint8_t bad_status[4] = {2, 50, 0, 50};
    const uint8_t bad_score[4] = {1, 101, 0, 50};
    const uint8_t bad_angle[4] = {1, 50, (uint8_t)(int8_t)-91, 50};
    const uint8_t bad_quality[4] = {1, 50, 0, 101};
    const uint8_t short_raw[3] = {1, 50, 0};
    sg_camera_face_metrics_t metrics = {0};

    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VALUE,
                      sg_camera_face_metrics_parse(bad_status, 4, &metrics));
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VALUE,
                      sg_camera_face_metrics_parse(bad_score, 4, &metrics));
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VALUE,
                      sg_camera_face_metrics_parse(bad_angle, 4, &metrics));
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VALUE,
                      sg_camera_face_metrics_parse(bad_quality, 4, &metrics));
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VALUE,
                      sg_camera_face_metrics_parse(short_raw, 3, &metrics));
}

TEST_CASE("vendor face bbox parses a detected face", "[camera_protocol]")
{
    const uint8_t raw[4] = {100, 80, 42, 36};
    sg_camera_face_bbox_t bbox = {0};
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_OK,
                      sg_camera_face_bbox_parse(raw, sizeof(raw), &bbox));
    TEST_ASSERT_TRUE(bbox.valid);
    TEST_ASSERT_EQUAL_UINT8(100, bbox.center_x);
    TEST_ASSERT_EQUAL_UINT8(80, bbox.center_y);
    TEST_ASSERT_EQUAL_UINT8(42, bbox.width);
    TEST_ASSERT_EQUAL_UINT8(36, bbox.height);
}

TEST_CASE("vendor face bbox treats all zero bytes as no face", "[camera_protocol]")
{
    const uint8_t raw[4] = {0, 0, 0, 0};
    sg_camera_face_bbox_t bbox = {
        .valid = true,
        .center_x = 1,
        .center_y = 1,
        .width = 1,
        .height = 1,
    };
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_OK,
                      sg_camera_face_bbox_parse(raw, sizeof(raw), &bbox));
    TEST_ASSERT_FALSE(bbox.valid);
    TEST_ASSERT_EQUAL_UINT8(0, bbox.width);
    TEST_ASSERT_EQUAL_UINT8(0, bbox.height);
}

TEST_CASE("vendor face bbox rejects short response", "[camera_protocol]")
{
    const uint8_t raw[3] = {100, 80, 42};
    sg_camera_face_bbox_t bbox = {0};
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_BAD_VALUE,
                      sg_camera_face_bbox_parse(raw, sizeof(raw), &bbox));
}

void app_main(void)
{
    unity_run_all_tests();
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
