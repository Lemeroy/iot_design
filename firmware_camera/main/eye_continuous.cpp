#include "eye_continuous.h"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace {

sg_eye_measurement_t sample_at(
    const sg_eye_continuous_context_t &context, uint8_t chronological_index)
{
    const uint8_t start = context.count < SG_EYE_CONTINUOUS_CAPACITY
        ? 0
        : context.next;
    return context.samples[
        (start + chronological_index) % SG_EYE_CONTINUOUS_CAPACITY];
}

sg_eye_continuous_result_t calculate(
    const sg_eye_continuous_context_t &context)
{
    sg_eye_continuous_result_t result = {};
    if (context.count < SG_EYE_CONTINUOUS_MIN_SAMPLES) return result;

    int difference_sum = 0;
    int quality_sum = 0;
    sg_eye_measurement_t previous = sample_at(context, 0);
    quality_sum += previous.quality;
    for (uint8_t i = 1; i < context.count; ++i) {
        const sg_eye_measurement_t current = sample_at(context, i);
        const int delta_left = current.left_x - previous.left_x;
        const int delta_right = current.right_x - previous.right_x;
        difference_sum += std::abs(delta_left - delta_right);
        quality_sum += current.quality;
        previous = current;
    }

    const float mean_difference =
        static_cast<float>(difference_sum) / (context.count - 1U);
    const float coherence = std::clamp(1.0f - mean_difference / 40.0f,
                                       0.0f, 1.0f);
    const float quality = static_cast<float>(quality_sum)
                        / context.count / 100.0f;
    const float usable = static_cast<float>(context.count)
                       / SG_EYE_CONTINUOUS_CAPACITY;
    result.valid = true;
    result.score = static_cast<uint8_t>(std::clamp(
        std::lround(100.0f * (0.45f * coherence + 0.35f * quality
                           + 0.20f * usable)), 0L, 100L));
    result.binocular_difference = static_cast<int8_t>(std::clamp(
        std::lround(mean_difference), 0L, 100L));
    result.quality = static_cast<uint8_t>(std::clamp(
        std::lround(quality * 100.0f), 0L, 100L));
    return result;
}

}  // namespace

extern "C" void sg_eye_continuous_init(sg_eye_continuous_context_t *context)
{
    if (context != nullptr) std::memset(context, 0, sizeof(*context));
}

extern "C" bool sg_eye_continuous_update(
    sg_eye_continuous_context_t *context,
    bool valid,
    const sg_eye_measurement_t *measurement,
    sg_eye_continuous_result_t *out)
{
    if (context == nullptr || out == nullptr) return false;
    if (!valid || measurement == nullptr) {
        if (++context->dropout_count > SG_EYE_CONTINUOUS_MAX_DROPOUT) {
            sg_eye_continuous_init(context);
        }
        *out = context->latest;
        return out->valid;
    }

    context->dropout_count = 0;
    context->samples[context->next] = *measurement;
    context->next = (context->next + 1U) % SG_EYE_CONTINUOUS_CAPACITY;
    if (context->count < SG_EYE_CONTINUOUS_CAPACITY) ++context->count;
    context->latest = calculate(*context);
    *out = context->latest;
    return out->valid;
}

extern "C" bool sg_eye_select_result(
    const sg_eye_continuous_result_t *continuous,
    const sg_camera_modal_metrics_t *guided,
    int64_t guided_us,
    int64_t now_us,
    sg_camera_modal_metrics_t *out)
{
    if (out == nullptr) return false;
    std::memset(out, 0, sizeof(*out));
    if (guided != nullptr && guided->valid && guided_us >= 0
        && now_us >= guided_us
        && now_us - guided_us <= SG_EYE_GUIDED_OVERRIDE_US) {
        *out = *guided;
        return true;
    }
    if (continuous == nullptr || !continuous->valid) return false;
    out->valid = true;
    out->score = continuous->score;
    out->signed_value = continuous->binocular_difference;
    out->quality = continuous->quality;
    return true;
}
