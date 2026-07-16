#include <cmath>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "unity.h"
#include "unity_test_runner.h"

#include "face_geometry.h"

static sg_face_geometry_input_t frontal_face()
{
    return {
        .box = {50, 30, 270, 220},
        .left_eye = {100, 90},
        .right_eye = {220, 90},
        .nose = {160, 130},
        .left_mouth = {125, 170},
        .right_mouth = {195, 170},
    };
}

TEST_CASE("level five-point face produces high F", "[face_geometry]")
{
    const auto input = frontal_face();
    sg_face_frame_metrics_t out = {};
    TEST_ASSERT_TRUE(sg_face_geometry_evaluate(&input, &out));
    TEST_ASSERT_GREATER_OR_EQUAL_UINT8(90, out.score);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 0.0f, out.mouth_angle_deg);
    TEST_ASSERT_LESS_OR_EQUAL_FLOAT(0.01f, out.corner_asymmetry);
}

TEST_CASE("displaced mouth corner lowers F", "[face_geometry]")
{
    auto input = frontal_face();
    input.right_mouth.y = 195;
    sg_face_frame_metrics_t out = {};
    TEST_ASSERT_TRUE(sg_face_geometry_evaluate(&input, &out));
    TEST_ASSERT_GREATER_OR_EQUAL_FLOAT(19.0f, std::fabs(out.mouth_angle_deg));
    TEST_ASSERT_LESS_OR_EQUAL_UINT8(25, out.score);
}

TEST_CASE("equal eye and mouth roll is corrected", "[face_geometry]")
{
    auto input = frontal_face();
    input.left_eye = {100, 80};
    input.right_eye = {220, 100};
    input.left_mouth = {125, 160};
    input.right_mouth = {195, 172};
    sg_face_frame_metrics_t out = {};
    TEST_ASSERT_TRUE(sg_face_geometry_evaluate(&input, &out));
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 0.0f, out.mouth_angle_deg);
    TEST_ASSERT_GREATER_OR_EQUAL_UINT8(85, out.score);
}

TEST_CASE("quality gate rejects small face", "[face_geometry]")
{
    auto input = frontal_face();
    input.box = {100, 50, 159, 210};
    sg_face_frame_metrics_t out = {};
    TEST_ASSERT_FALSE(sg_face_geometry_evaluate(&input, &out));
}

TEST_CASE("quality gate rejects short eye distance", "[face_geometry]")
{
    auto input = frontal_face();
    input.left_eye = {155, 90};
    input.right_eye = {165, 90};
    sg_face_frame_metrics_t out = {};
    TEST_ASSERT_FALSE(sg_face_geometry_evaluate(&input, &out));
}

TEST_CASE("quality gate rejects off-center nose", "[face_geometry]")
{
    auto input = frontal_face();
    input.nose.x = 100;
    sg_face_frame_metrics_t out = {};
    TEST_ASSERT_FALSE(sg_face_geometry_evaluate(&input, &out));
}

TEST_CASE("quality gate rejects mouth above eyes", "[face_geometry]")
{
    auto input = frontal_face();
    input.left_mouth.y = 70;
    input.right_mouth.y = 70;
    sg_face_frame_metrics_t out = {};
    TEST_ASSERT_FALSE(sg_face_geometry_evaluate(&input, &out));
}

extern "C" void app_main(void)
{
    unity_run_all_tests();
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
