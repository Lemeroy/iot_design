#include "face_stabilizer.h"

#include <string.h>

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

void sg_face_stabilizer_reset(sg_face_stabilizer_t *state)
{
    if (state != NULL) {
        memset(state, 0, sizeof(*state));
    }
}

bool sg_face_stabilizer_push(
    sg_face_stabilizer_t *state,
    const sg_face_frame_metrics_t *sample,
    sg_face_frame_metrics_t *out)
{
    if (state == NULL || sample == NULL || out == NULL) return false;

    const size_t index = state->next;
    state->scores[index] = sample->score;
    state->angles[index] = sample->mouth_angle_deg;
    state->asymmetries[index] = sample->corner_asymmetry;
    state->qualities[index] = sample->quality;
    state->next = (index + 1U) % SG_FACE_STABILIZER_SAMPLES;
    if (state->count < SG_FACE_STABILIZER_SAMPLES) {
        ++state->count;
    }
    if (state->count < SG_FACE_STABILIZER_SAMPLES) {
        memset(out, 0, sizeof(*out));
        return false;
    }

    uint8_t scores[SG_FACE_STABILIZER_SAMPLES];
    float angles[SG_FACE_STABILIZER_SAMPLES];
    float asymmetries[SG_FACE_STABILIZER_SAMPLES];
    uint8_t qualities[SG_FACE_STABILIZER_SAMPLES];
    memcpy(scores, state->scores, sizeof(scores));
    memcpy(angles, state->angles, sizeof(angles));
    memcpy(asymmetries, state->asymmetries, sizeof(asymmetries));
    memcpy(qualities, state->qualities, sizeof(qualities));
    sort_u8(scores, SG_FACE_STABILIZER_SAMPLES);
    sort_float(angles, SG_FACE_STABILIZER_SAMPLES);
    sort_float(asymmetries, SG_FACE_STABILIZER_SAMPLES);
    sort_u8(qualities, SG_FACE_STABILIZER_SAMPLES);

    const size_t median = SG_FACE_STABILIZER_SAMPLES / 2U;
    out->score = scores[median];
    out->mouth_angle_deg = angles[median];
    out->corner_asymmetry = asymmetries[median];
    out->quality = qualities[median];
    return true;
}
