#include <cmath>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "unity.h"
#include "unity_test_runner.h"

#include "face_geometry.h"
#include "face_stabilizer.h"

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

TEST_CASE("stabilizer publishes median after five samples", "[face_stabilizer]")
{
    sg_face_stabilizer_t state = {};
    const uint8_t scores[5] = {90, 92, 10, 91, 93};
    const float angles[5] = {1.0f, 2.0f, 30.0f, 0.0f, -1.0f};
    const uint8_t qualities[5] = {80, 82, 20, 81, 83};
    sg_face_frame_metrics_t stable = {};

    for (int i = 0; i < 4; ++i) {
        const sg_face_frame_metrics_t sample = {
            .score = scores[i],
            .mouth_angle_deg = angles[i],
            .corner_asymmetry = 0.0f,
            .quality = qualities[i],
        };
        TEST_ASSERT_FALSE(sg_face_stabilizer_push(&state, &sample, &stable));
    }
    const sg_face_frame_metrics_t fifth = {
        .score = scores[4],
        .mouth_angle_deg = angles[4],
        .corner_asymmetry = 0.0f,
        .quality = qualities[4],
    };
    TEST_ASSERT_TRUE(sg_face_stabilizer_push(&state, &fifth, &stable));
    TEST_ASSERT_EQUAL_UINT8(91, stable.score);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 1.0f, stable.mouth_angle_deg);
    TEST_ASSERT_EQUAL_UINT8(81, stable.quality);
}

TEST_CASE("stabilizer reset requires five new samples", "[face_stabilizer]")
{
    sg_face_stabilizer_t state = {};
    const sg_face_frame_metrics_t sample = {
        .score = 88,
        .mouth_angle_deg = 3.0f,
        .corner_asymmetry = 0.1f,
        .quality = 75,
    };
    sg_face_frame_metrics_t stable = {};
    for (int i = 0; i < 5; ++i) {
        (void)sg_face_stabilizer_push(&state, &sample, &stable);
    }
    sg_face_stabilizer_reset(&state);
    for (int i = 0; i < 4; ++i) {
        TEST_ASSERT_FALSE(sg_face_stabilizer_push(&state, &sample, &stable));
    }
    TEST_ASSERT_TRUE(sg_face_stabilizer_push(&state, &sample, &stable));
}

extern "C" void app_main(void)
{
    unity_run_all_tests();
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
