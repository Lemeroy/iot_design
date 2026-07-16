#include <algorithm>
#include <cstdint>
#include <cstring>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "unity.h"
#include "unity_test_runner.h"

#include "eye_tracking.h"

static constexpr int WIDTH = 80;
static constexpr int HEIGHT = 40;
static uint8_t image[WIDTH * HEIGHT * 3];

static void fill_rgb(uint8_t value)
{
    std::memset(image, value, sizeof(image));
}

static void dark_disc(int cx, int cy, int radius, uint8_t value = 10)
{
    for (int y = cy - radius; y <= cy + radius; ++y) {
        for (int x = cx - radius; x <= cx + radius; ++x) {
            if (x < 0 || y < 0 || x >= WIDTH || y >= HEIGHT) continue;
            if ((x - cx) * (x - cx) + (y - cy) * (y - cy) > radius * radius) continue;
            uint8_t *pixel = &image[(y * WIDTH + x) * 3];
            pixel[0] = value;
            pixel[1] = value;
            pixel[2] = value;
        }
    }
}

static sg_eye_input_t input_for_centers(int left_x = 24, int right_x = 56)
{
    return {
        .rgb888 = image,
        .width = WIDTH,
        .height = HEIGHT,
        .stride_bytes = WIDTH * 3,
        .left_eye = {(int16_t)left_x, 20},
        .right_eye = {(int16_t)right_x, 20},
        .inter_eye_distance = 32,
        .eye_line_angle_deg = 0.0f,
    };
}

TEST_CASE("eye kernel locates centered pupils", "[eye_tracking]")
{
    fill_rgb(220);
    dark_disc(24, 20, 2);
    dark_disc(56, 20, 2);
    const auto input = input_for_centers();
    sg_eye_measurement_t out = {};
    TEST_ASSERT_TRUE(sg_eye_measure(&input, &out));
    TEST_ASSERT_INT8_WITHIN(8, 0, out.left_x);
    TEST_ASSERT_INT8_WITHIN(8, 0, out.right_x);
    TEST_ASSERT_GREATER_OR_EQUAL_UINT8(60, out.quality);
}

TEST_CASE("eye kernel measures common horizontal displacement", "[eye_tracking]")
{
    fill_rgb(220);
    dark_disc(20, 20, 2);
    dark_disc(52, 20, 2);
    const auto input = input_for_centers();
    sg_eye_measurement_t out = {};
    TEST_ASSERT_TRUE(sg_eye_measure(&input, &out));
    TEST_ASSERT_LESS_THAN_INT8(-20, out.left_x);
    TEST_ASSERT_LESS_THAN_INT8(-20, out.right_x);
    TEST_ASSERT_INT8_WITHIN(10, out.left_x, out.right_x);
}

TEST_CASE("eye kernel rejects low contrast", "[eye_tracking]")
{
    fill_rgb(120);
    const auto input = input_for_centers();
    sg_eye_measurement_t out = {};
    TEST_ASSERT_FALSE(sg_eye_measure(&input, &out));
}

TEST_CASE("eye kernel rejects implausibly dark eye regions", "[eye_tracking]")
{
    fill_rgb(220);
    for (int y = 16; y <= 24; ++y) {
        for (int x = 17; x <= 31; ++x) {
            uint8_t *pixel = &image[(y * WIDTH + x) * 3];
            pixel[0] = pixel[1] = pixel[2] = 5;
        }
    }
    dark_disc(56, 20, 2);
    const auto input = input_for_centers();
    sg_eye_measurement_t out = {};
    TEST_ASSERT_FALSE(sg_eye_measure(&input, &out));
}

TEST_CASE("eye kernel rejects clipped regions", "[eye_tracking]")
{
    fill_rgb(220);
    dark_disc(2, 20, 2);
    dark_disc(34, 20, 2);
    const auto input = input_for_centers(2, 34);
    sg_eye_measurement_t out = {};
    TEST_ASSERT_FALSE(sg_eye_measure(&input, &out));
}

static sg_eye_measurement_t measured(int left, int right, int quality = 85)
{
    return {
        .left_x = (int8_t)left,
        .right_x = (int8_t)right,
        .quality = (uint8_t)quality,
    };
}

TEST_CASE("eye sequence accepts conjugate opposite gaze steps", "[eye_tracking]")
{
    const auto center = measured(0, 2);
    const auto left = measured(-45, -42);
    const auto right = measured(43, 47);
    sg_eye_sequence_result_t out = {};
    TEST_ASSERT_TRUE(sg_eye_score_sequence(&center, &left, &right, &out));
    TEST_ASSERT_GREATER_OR_EQUAL_UINT8(85, out.score);
    TEST_ASSERT_LESS_OR_EQUAL_INT8(10, out.binocular_difference);
}

TEST_CASE("eye sequence lowers discordant movement", "[eye_tracking]")
{
    const auto center = measured(0, 0);
    const auto left = measured(-45, 35);
    const auto right = measured(45, -35);
    sg_eye_sequence_result_t out = {};
    TEST_ASSERT_TRUE(sg_eye_score_sequence(&center, &left, &right, &out));
    TEST_ASSERT_LESS_OR_EQUAL_UINT8(30, out.score);
    TEST_ASSERT_GREATER_OR_EQUAL_INT8(50, out.binocular_difference);
}

TEST_CASE("eye sequence rejects insufficient travel", "[eye_tracking]")
{
    const auto center = measured(0, 0);
    const auto left = measured(-5, -4);
    const auto right = measured(4, 5);
    sg_eye_sequence_result_t out = {};
    TEST_ASSERT_FALSE(sg_eye_score_sequence(&center, &left, &right, &out));
}

extern "C" void app_main(void)
{
    unity_run_all_tests();
    while (true) vTaskDelay(pdMS_TO_TICKS(1000));
}
