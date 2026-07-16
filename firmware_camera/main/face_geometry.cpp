#include "face_geometry.h"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace {

constexpr int kMinFaceWidth = 64;
constexpr float kMinEyeDistance = 20.0f;
constexpr float kMaxEyeRollDeg = 25.0f;
constexpr float kAngleHealthyDeg = 2.0f;
constexpr float kAngleZeroDeg = 20.0f;
constexpr float kAsymmetryHealthy = 0.05f;
constexpr float kAsymmetryZero = 0.35f;
constexpr float kRadToDeg = 57.29577951308232f;

float point_distance(const sg_face_point_t &a, const sg_face_point_t &b)
{
    return std::hypot(static_cast<float>(b.x - a.x),
                      static_cast<float>(b.y - a.y));
}

float line_angle_deg(const sg_face_point_t &left, const sg_face_point_t &right)
{
    return std::atan2(static_cast<float>(right.y - left.y),
                      static_cast<float>(right.x - left.x)) * kRadToDeg;
}

float normalize_half_turn(float angle)
{
    while (angle > 90.0f) angle -= 180.0f;
    while (angle < -90.0f) angle += 180.0f;
    return angle;
}

bool point_in_box(const sg_face_point_t &point, const sg_face_box_t &box)
{
    return point.x >= box.x0 && point.x <= box.x1
        && point.y >= box.y0 && point.y <= box.y1;
}

float descending_score(float value, float healthy, float zero)
{
    if (value <= healthy) return 100.0f;
    if (value >= zero) return 0.0f;
    return 100.0f * (zero - value) / (zero - healthy);
}

uint8_t rounded_u8(float value)
{
    return static_cast<uint8_t>(std::lround(std::clamp(value, 0.0f, 100.0f)));
}

}  // namespace

extern "C" bool sg_face_geometry_evaluate(
    const sg_face_geometry_input_t *input,
    sg_face_frame_metrics_t *out)
{
    if (out == nullptr) return false;
    std::memset(out, 0, sizeof(*out));
    if (input == nullptr) return false;

    const int face_width = input->box.x1 - input->box.x0 + 1;
    if (face_width < kMinFaceWidth
        || input->left_eye.x >= input->right_eye.x
        || input->left_mouth.x >= input->right_mouth.x
        || !point_in_box(input->nose, input->box)
        || !point_in_box(input->left_mouth, input->box)
        || !point_in_box(input->right_mouth, input->box)) {
        return false;
    }

    const float eye_distance = point_distance(input->left_eye, input->right_eye);
    const float eye_angle = line_angle_deg(input->left_eye, input->right_eye);
    if (eye_distance < kMinEyeDistance
        || std::fabs(eye_angle) > kMaxEyeRollDeg) {
        return false;
    }

    const float eye_span = static_cast<float>(
        input->right_eye.x - input->left_eye.x);
    const float nose_min_x = input->left_eye.x + 0.25f * eye_span;
    const float nose_max_x = input->left_eye.x + 0.75f * eye_span;
    const float eye_mid_y = 0.5f * (input->left_eye.y + input->right_eye.y);
    const float mouth_mid_y = 0.5f * (
        input->left_mouth.y + input->right_mouth.y);
    if (input->nose.x < nose_min_x || input->nose.x > nose_max_x
        || mouth_mid_y <= eye_mid_y) {
        return false;
    }

    const float mouth_angle = normalize_half_turn(
        line_angle_deg(input->left_mouth, input->right_mouth) - eye_angle);
    const float left_distance = point_distance(input->nose, input->left_mouth);
    const float right_distance = point_distance(input->nose, input->right_mouth);
    const float distance_sum = left_distance + right_distance;
    if (distance_sum <= 0.0f) return false;
    const float corner_asymmetry =
        std::fabs(left_distance - right_distance) / distance_sum;

    const float angle_score = descending_score(
        std::fabs(mouth_angle), kAngleHealthyDeg, kAngleZeroDeg);
    const float asymmetry_score = descending_score(
        corner_asymmetry, kAsymmetryHealthy, kAsymmetryZero);

    const float size_quality = std::clamp(
        100.0f * (face_width - kMinFaceWidth) / 96.0f, 0.0f, 100.0f);
    const float eye_quality = std::clamp(
        100.0f * (eye_distance - kMinEyeDistance) / 60.0f, 0.0f, 100.0f);
    const float nose_offset = std::fabs(
        input->nose.x - 0.5f * (input->left_eye.x + input->right_eye.x));
    const float nose_quality = std::clamp(
        100.0f * (1.0f - nose_offset / (0.25f * eye_span)), 0.0f, 100.0f);
    const float roll_quality = std::clamp(
        100.0f * (1.0f - std::fabs(eye_angle) / kMaxEyeRollDeg),
        0.0f, 100.0f);

    out->score = rounded_u8(0.75f * angle_score + 0.25f * asymmetry_score);
    out->mouth_angle_deg = mouth_angle;
    out->corner_asymmetry = corner_asymmetry;
    out->quality = rounded_u8(
        0.25f * (size_quality + eye_quality + nose_quality + roll_quality));
    return true;
}
