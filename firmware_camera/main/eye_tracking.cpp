#include "eye_tracking.h"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace {

constexpr float kPi = 3.14159265358979323846f;
constexpr int kMinContrast = 30;
constexpr int kMinDarkPercent = 2;
constexpr int kMaxDarkPercent = 40;
constexpr int kMinTravel = 15;

struct EyeResult {
    int8_t x;
    uint8_t quality;
};

int intensity(const uint8_t *pixel)
{
    return (77 * pixel[0] + 150 * pixel[1] + 29 * pixel[2]) >> 8;
}

bool measure_one(
    const sg_eye_input_t &input,
    const sg_eye_point_t &center,
    int half_width,
    int half_height,
    EyeResult &out)
{
    const float radians = input.eye_line_angle_deg * kPi / 180.0f;
    const float cosine = std::cos(radians);
    const float sine = std::sin(radians);
    int minimum = 255;
    int maximum = 0;

    for (int local_y = -half_height; local_y <= half_height; ++local_y) {
        for (int local_x = -half_width; local_x <= half_width; ++local_x) {
            const int x = (int)std::lround(center.x + local_x * cosine - local_y * sine);
            const int y = (int)std::lround(center.y + local_x * sine + local_y * cosine);
            if (x < 0 || y < 0 || x >= input.width || y >= input.height) return false;
            const int value = intensity(input.rgb888 + y * input.stride_bytes + x * 3);
            minimum = std::min(minimum, value);
            maximum = std::max(maximum, value);
        }
    }
    const int contrast = maximum - minimum;
    if (contrast < kMinContrast) return false;
    const int threshold = minimum + contrast * 35 / 100;
    int count = 0;
    int sum_local_x = 0;
    const int area = (half_width * 2 + 1) * (half_height * 2 + 1);

    for (int local_y = -half_height; local_y <= half_height; ++local_y) {
        for (int local_x = -half_width; local_x <= half_width; ++local_x) {
            const int x = (int)std::lround(center.x + local_x * cosine - local_y * sine);
            const int y = (int)std::lround(center.y + local_x * sine + local_y * cosine);
            const int value = intensity(input.rgb888 + y * input.stride_bytes + x * 3);
            if (value <= threshold) {
                ++count;
                sum_local_x += local_x;
            }
        }
    }
    const int dark_percent = count * 100 / area;
    if (count == 0 || dark_percent < kMinDarkPercent
        || dark_percent > kMaxDarkPercent) {
        return false;
    }
    const int normalized_x = (sum_local_x * 100) / (count * half_width);
    out.x = (int8_t)std::clamp(normalized_x, -100, 100);
    out.quality = (uint8_t)std::clamp((contrast - kMinContrast) * 100 / 150, 0, 100);
    return true;
}

}  // namespace

extern "C" bool sg_eye_measure(
    const sg_eye_input_t *input, sg_eye_measurement_t *out)
{
    if (input == nullptr || out == nullptr || input->rgb888 == nullptr
        || input->width == 0 || input->height == 0
        || input->stride_bytes < input->width * 3U
        || input->inter_eye_distance < 12U
        || std::fabs(input->eye_line_angle_deg) > 25.0f) {
        return false;
    }
    std::memset(out, 0, sizeof(*out));
    const int half_width = std::max(3, (int)input->inter_eye_distance * 22 / 100);
    const int half_height = std::max(2, (int)input->inter_eye_distance * 14 / 100);
    EyeResult left = {};
    EyeResult right = {};
    if (!measure_one(*input, input->left_eye, half_width, half_height, left)
        || !measure_one(*input, input->right_eye, half_width, half_height, right)) {
        return false;
    }
    out->left_x = left.x;
    out->right_x = right.x;
    out->quality = std::min(left.quality, right.quality);
    return true;
}

extern "C" bool sg_eye_score_sequence(
    const sg_eye_measurement_t *center,
    const sg_eye_measurement_t *left,
    const sg_eye_measurement_t *right,
    sg_eye_sequence_result_t *out)
{
    if (center == nullptr || left == nullptr || right == nullptr || out == nullptr) {
        return false;
    }
    std::memset(out, 0, sizeof(*out));
    const int left_l = left->left_x - center->left_x;
    const int left_r = left->right_x - center->right_x;
    const int right_l = right->left_x - center->left_x;
    const int right_r = right->right_x - center->right_x;
    const int left_mean = (left_l + left_r) / 2;
    const int right_mean = (right_l + right_r) / 2;
    const int left_travel = std::max(std::abs(left_l), std::abs(left_r));
    const int right_travel = std::max(std::abs(right_l), std::abs(right_r));
    const int directional_travel = std::min(left_travel, right_travel);
    if (directional_travel < kMinTravel) return false;

    const int difference = std::max(
        std::abs(left_l - left_r), std::abs(right_l - right_r));
    const bool conjugate = left_l * left_r > 0 && right_l * right_r > 0;
    const bool opposite_steps = left_mean * right_mean < 0;
    const int agreement_score = std::clamp(100 - difference, 0, 100);
    const int travel_score = std::clamp(directional_travel * 2, 0, 100);
    out->score = (uint8_t)((conjugate && opposite_steps)
        ? (agreement_score * 7 + travel_score * 3) / 10
        : 0);
    out->binocular_difference = (int8_t)std::clamp(difference, 0, 100);
    out->quality = std::min({center->quality, left->quality, right->quality});
    return true;
}
