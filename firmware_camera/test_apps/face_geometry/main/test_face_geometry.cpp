#include <cmath>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "unity.h"
#include "unity_test_runner.h"

#include "face_geometry.h"
#include "face_baseline.h"
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

static sg_face_frame_metrics_t baseline_sample(float angle, float asymmetry,
                                                uint8_t quality = 85)
{
    return {
        .score = 100,
        .mouth_angle_deg = angle,
        .corner_asymmetry = asymmetry,
        .quality = quality,
    };
}

static void establish_baseline(sg_face_baseline_t *state, int64_t start_us)
{
    const float angles[5] = {1.0f, 1.2f, 0.8f, 1.1f, 0.9f};
    const float asymmetries[5] = {0.050f, 0.052f, 0.048f, 0.051f, 0.049f};
    sg_face_frame_metrics_t out = {};
    for (int i = 0; i < 5; ++i) {
        const auto sample = baseline_sample(angles[i], asymmetries[i]);
        TEST_ASSERT_FALSE(sg_face_baseline_update(
            state, &sample, start_us + i * 500000LL, &out));
    }
    TEST_ASSERT_TRUE(sg_face_baseline_ready(state));
}

TEST_CASE("personal baseline calibrates from five stable samples", "[face_baseline]")
{
    sg_face_baseline_t state = {};
    establish_baseline(&state, 1000000LL);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 1.0f, state.baseline_angle_deg);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.050f, state.baseline_asymmetry);
}

TEST_CASE("personal baseline rejects low quality and unstable windows", "[face_baseline]")
{
    sg_face_baseline_t state = {};
    sg_face_frame_metrics_t out = {};
    for (int i = 0; i < 5; ++i) {
        const auto low_quality = baseline_sample(1.0f, 0.05f, 69);
        TEST_ASSERT_FALSE(sg_face_baseline_update(
            &state, &low_quality, 1000000LL + i * 500000LL, &out));
    }
    TEST_ASSERT_FALSE(sg_face_baseline_ready(&state));

    sg_face_baseline_reset(&state);
    const float unstable[5] = {0.0f, 0.0f, 0.0f, 0.0f, 4.0f};
    for (int i = 0; i < 5; ++i) {
        const auto sample = baseline_sample(unstable[i], 0.05f);
        TEST_ASSERT_FALSE(sg_face_baseline_update(
            &state, &sample, 5000000LL + i * 500000LL, &out));
    }
    TEST_ASSERT_FALSE(sg_face_baseline_ready(&state));
}

TEST_CASE("relative score responds after three frames", "[face_baseline]")
{
    sg_face_baseline_t state = {};
    establish_baseline(&state, 1000000LL);
    sg_face_frame_metrics_t out = {};

    const auto neutral = baseline_sample(1.0f, 0.05f);
    TEST_ASSERT_FALSE(sg_face_baseline_update(&state, &neutral, 4000000LL, &out));
    TEST_ASSERT_FALSE(sg_face_baseline_update(&state, &neutral, 4500000LL, &out));
    TEST_ASSERT_TRUE(sg_face_baseline_update(&state, &neutral, 5000000LL, &out));
    TEST_ASSERT_GREATER_OR_EQUAL_UINT8(95, out.score);

    const auto changed = baseline_sample(9.0f, 0.20f);
    TEST_ASSERT_TRUE(sg_face_baseline_update(&state, &changed, 5500000LL, &out));
    TEST_ASSERT_TRUE(sg_face_baseline_update(&state, &changed, 6000000LL, &out));
    TEST_ASSERT_TRUE(sg_face_baseline_update(&state, &changed, 6500000LL, &out));
    TEST_ASSERT_LESS_OR_EQUAL_UINT8(5, out.score);
}

TEST_CASE("personal baseline survives brief gap and resets at ten seconds", "[face_baseline]")
{
    sg_face_baseline_t state = {};
    establish_baseline(&state, 1000000LL);
    const int64_t last_valid = state.last_valid_us;
    sg_face_baseline_note_invalid(&state, last_valid + 9000000LL);
    TEST_ASSERT_TRUE(sg_face_baseline_ready(&state));
    sg_face_baseline_note_invalid(&state, last_valid + 10000000LL);
    TEST_ASSERT_FALSE(sg_face_baseline_ready(&state));
}

extern "C" void app_main(void)
{
    unity_run_all_tests();
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
