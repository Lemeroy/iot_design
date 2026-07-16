#include "face_baseline.h"

#include <math.h>
#include <string.h>

#define SG_FACE_BASELINE_MIN_QUALITY 70U
#define SG_FACE_BASELINE_MAX_ANGLE_RANGE 2.0f
#define SG_FACE_BASELINE_MAX_ASYMMETRY_RANGE 0.03f
#define SG_FACE_RELATIVE_ANGLE_HEALTHY 0.5f
#define SG_FACE_RELATIVE_ANGLE_ZERO 8.0f
#define SG_FACE_RELATIVE_ASYMMETRY_HEALTHY 0.01f
#define SG_FACE_RELATIVE_ASYMMETRY_ZERO 0.15f

static void sort_float(float *values, size_t length)
{
    for (size_t i = 1; i < length; ++i) {
        float value = values[i];
        size_t j = i;
        while (j > 0 && values[j - 1] > value) {
            values[j] = values[j - 1];
            --j;
        }
        values[j] = value;
    }
}

static void sort_u8(uint8_t *values, size_t length)
{
    for (size_t i = 1; i < length; ++i) {
        uint8_t value = values[i];
        size_t j = i;
        while (j > 0 && values[j - 1] > value) {
            values[j] = values[j - 1];
            --j;
        }
        values[j] = value;
    }
}

static float descending_score(float value, float healthy, float zero)
{
    if (value <= healthy) return 100.0f;
    if (value >= zero) return 0.0f;
    return 100.0f * (zero - value) / (zero - healthy);
}

static uint8_t bounded_round(float value)
{
    if (value <= 0.0f) return 0U;
    if (value >= 100.0f) return 100U;
    return (uint8_t)lroundf(value);
}

void sg_face_baseline_reset(sg_face_baseline_t *state)
{
    if (state != NULL) memset(state, 0, sizeof(*state));
}

bool sg_face_baseline_ready(const sg_face_baseline_t *state)
{
    return state != NULL && state->state == SG_FACE_BASELINE_READY;
}

void sg_face_baseline_note_invalid(sg_face_baseline_t *state, int64_t now_us)
{
    if (state == NULL) return;
    if (state->state == SG_FACE_BASELINE_CALIBRATING) {
        state->state = SG_FACE_BASELINE_WAITING;
        state->calibration_count = 0U;
        return;
    }
    if (state->state == SG_FACE_BASELINE_READY && state->last_valid_us > 0
        && now_us - state->last_valid_us >= SG_FACE_BASELINE_RESET_US) {
        sg_face_baseline_reset(state);
    }
}

static void calibration_add(
    sg_face_baseline_t *state, const sg_face_frame_metrics_t *sample)
{
    const size_t index = state->calibration_count++;
    state->calibration_angles[index] = sample->mouth_angle_deg;
    state->calibration_asymmetries[index] = sample->corner_asymmetry;
}

static bool calibration_finish(sg_face_baseline_t *state)
{
    float angles[SG_FACE_BASELINE_CALIBRATION_SAMPLES];
    float asymmetries[SG_FACE_BASELINE_CALIBRATION_SAMPLES];
    memcpy(angles, state->calibration_angles, sizeof(angles));
    memcpy(asymmetries, state->calibration_asymmetries, sizeof(asymmetries));
    sort_float(angles, SG_FACE_BASELINE_CALIBRATION_SAMPLES);
    sort_float(asymmetries, SG_FACE_BASELINE_CALIBRATION_SAMPLES);
    if (angles[4] - angles[0] > SG_FACE_BASELINE_MAX_ANGLE_RANGE
        || asymmetries[4] - asymmetries[0]
            > SG_FACE_BASELINE_MAX_ASYMMETRY_RANGE) {
        const float latest_angle = state->calibration_angles[4];
        const float latest_asymmetry = state->calibration_asymmetries[4];
        state->calibration_count = 1U;
        state->calibration_angles[0] = latest_angle;
        state->calibration_asymmetries[0] = latest_asymmetry;
        return false;
    }
    state->baseline_angle_deg = angles[2];
    state->baseline_asymmetry = asymmetries[2];
    state->state = SG_FACE_BASELINE_READY;
    state->output_count = 0U;
    state->output_next = 0U;
    return true;
}

static bool output_add(
    sg_face_baseline_t *state,
    const sg_face_frame_metrics_t *sample,
    uint8_t relative_score,
    sg_face_frame_metrics_t *out)
{
    const size_t index = state->output_next;
    state->output_scores[index] = relative_score;
    state->output_angles[index] = sample->mouth_angle_deg;
    state->output_asymmetries[index] = sample->corner_asymmetry;
    state->output_qualities[index] = sample->quality;
    state->output_next = (index + 1U) % SG_FACE_BASELINE_OUTPUT_SAMPLES;
    if (state->output_count < SG_FACE_BASELINE_OUTPUT_SAMPLES) {
        ++state->output_count;
    }
    if (state->output_count < SG_FACE_BASELINE_OUTPUT_SAMPLES) return false;

    uint8_t scores[SG_FACE_BASELINE_OUTPUT_SAMPLES];
    float angles[SG_FACE_BASELINE_OUTPUT_SAMPLES];
    float asymmetries[SG_FACE_BASELINE_OUTPUT_SAMPLES];
    uint8_t qualities[SG_FACE_BASELINE_OUTPUT_SAMPLES];
    memcpy(scores, state->output_scores, sizeof(scores));
    memcpy(angles, state->output_angles, sizeof(angles));
    memcpy(asymmetries, state->output_asymmetries, sizeof(asymmetries));
    memcpy(qualities, state->output_qualities, sizeof(qualities));
    sort_u8(scores, SG_FACE_BASELINE_OUTPUT_SAMPLES);
    sort_float(angles, SG_FACE_BASELINE_OUTPUT_SAMPLES);
    sort_float(asymmetries, SG_FACE_BASELINE_OUTPUT_SAMPLES);
    sort_u8(qualities, SG_FACE_BASELINE_OUTPUT_SAMPLES);
    out->score = scores[1];
    out->mouth_angle_deg = angles[1];
    out->corner_asymmetry = asymmetries[1];
    out->quality = qualities[1];
    return true;
}

bool sg_face_baseline_update(
    sg_face_baseline_t *state,
    const sg_face_frame_metrics_t *sample,
    int64_t now_us,
    sg_face_frame_metrics_t *out)
{
    if (state == NULL || sample == NULL || out == NULL || now_us <= 0) {
        return false;
    }
    memset(out, 0, sizeof(*out));
    if (sample->quality < SG_FACE_BASELINE_MIN_QUALITY) {
        sg_face_baseline_note_invalid(state, now_us);
        return false;
    }
    state->last_valid_us = now_us;

    if (state->state != SG_FACE_BASELINE_READY) {
        if (state->state == SG_FACE_BASELINE_WAITING) {
            state->state = SG_FACE_BASELINE_CALIBRATING;
            state->calibration_count = 0U;
        }
        calibration_add(state, sample);
        if (state->calibration_count == SG_FACE_BASELINE_CALIBRATION_SAMPLES) {
            (void)calibration_finish(state);
        }
        return false;
    }

    const float angle_delta = fabsf(
        sample->mouth_angle_deg - state->baseline_angle_deg);
    const float asymmetry_delta = fabsf(
        sample->corner_asymmetry - state->baseline_asymmetry);
    const float angle_score = descending_score(
        angle_delta, SG_FACE_RELATIVE_ANGLE_HEALTHY,
        SG_FACE_RELATIVE_ANGLE_ZERO);
    const float asymmetry_score = descending_score(
        asymmetry_delta, SG_FACE_RELATIVE_ASYMMETRY_HEALTHY,
        SG_FACE_RELATIVE_ASYMMETRY_ZERO);
    const uint8_t relative_score = bounded_round(
        0.75f * angle_score + 0.25f * asymmetry_score);
    return output_add(state, sample, relative_score, out);
}
