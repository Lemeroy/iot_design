#include "screening_session.h"

#include <stdlib.h>
#include <string.h>

#define SG_STAGE_SETTLE_US 500000LL
#define SG_STAGE_TIMEOUT_GRACE_US 5000000LL
#define SG_FACE_DURATION_US 3000000LL
#define SG_FACE_DEADLINE_US 20000000LL
#define SG_EYE_DURATION_US 4000000LL
#define SG_TONGUE_DURATION_US 3000000LL
#define SG_FACE_SAMPLE_WINDOW 5U
#define SG_FACE_SAMPLE_MASK 0x1FU
#define SG_SCREENING_FACE_REQUIRED_SAMPLES 2U

static int64_t stage_duration(sg_screening_stage_t stage)
{
    if (stage == SG_STAGE_FACE) return SG_FACE_DURATION_US;
    if (stage == SG_STAGE_EYE_CENTER || stage == SG_STAGE_EYE_LEFT
        || stage == SG_STAGE_EYE_RIGHT) return SG_EYE_DURATION_US;
    if (stage == SG_STAGE_TONGUE) return SG_TONGUE_DURATION_US;
    return 0;
}

static int compare_i8(const void *left, const void *right)
{
    const int a = *(const int8_t *)left;
    const int b = *(const int8_t *)right;
    return (a > b) - (a < b);
}

static int compare_u8(const void *left, const void *right)
{
    const int a = *(const uint8_t *)left;
    const int b = *(const uint8_t *)right;
    return (a > b) - (a < b);
}

static sg_eye_measurement_t median_eye(const sg_eye_measurement_t *samples)
{
    int8_t left[3];
    int8_t right[3];
    uint8_t quality[3];
    for (size_t i = 0; i < 3; ++i) {
        left[i] = samples[i].left_x;
        right[i] = samples[i].right_x;
        quality[i] = samples[i].quality;
    }
    qsort(left, 3, sizeof(left[0]), compare_i8);
    qsort(right, 3, sizeof(right[0]), compare_i8);
    qsort(quality, 3, sizeof(quality[0]), compare_u8);
    const sg_eye_measurement_t out = {
        .left_x = left[1], .right_x = right[1], .quality = quality[1],
    };
    return out;
}

static sg_tongue_measurement_t median_tongue(
    const sg_tongue_measurement_t *samples)
{
    int8_t offset[3];
    uint8_t score[3];
    uint8_t quality[3];
    for (size_t i = 0; i < 3; ++i) {
        offset[i] = samples[i].signed_offset;
        score[i] = samples[i].score;
        quality[i] = samples[i].quality;
    }
    qsort(offset, 3, sizeof(offset[0]), compare_i8);
    qsort(score, 3, sizeof(score[0]), compare_u8);
    qsort(quality, 3, sizeof(quality[0]), compare_u8);
    const sg_tongue_measurement_t out = {
        .signed_offset = offset[1], .score = score[1], .quality = quality[1],
    };
    return out;
}

static void enter_stage(
    sg_screening_session_t *session, sg_screening_stage_t stage, int64_t now_us)
{
    session->stage = stage;
    session->stage_started_us = now_us;
    session->sample_count = 0;
    session->sample_next = 0;
    session->face_sample_window = 0;
    session->face_window_count = 0;
    memset(session->eye_samples, 0, sizeof(session->eye_samples));
    memset(session->tongue_samples, 0, sizeof(session->tongue_samples));
}

void sg_screening_session_start(sg_screening_session_t *session, int64_t now_us)
{
    if (session == NULL || now_us <= 0) return;
    memset(session, 0, sizeof(*session));
    enter_stage(session, SG_STAGE_FACE, now_us);
}

void sg_screening_session_cancel(sg_screening_session_t *session)
{
    if (session == NULL) return;
    memset(session, 0, sizeof(*session));
    session->stage = SG_STAGE_IDLE;
}

static uint8_t count_face_samples(uint8_t window)
{
    uint8_t count = 0;
    while (window != 0) {
        count += window & 1U;
        window >>= 1U;
    }
    return count;
}

static void add_sample(
    sg_screening_session_t *session, const sg_screening_sample_t *sample)
{
    if (session->stage == SG_STAGE_FACE) {
        session->face_sample_window = (uint8_t)(
            ((session->face_sample_window << 1U)
             | (sample->face_ready ? 1U : 0U)) & SG_FACE_SAMPLE_MASK);
        if (session->face_window_count < SG_FACE_SAMPLE_WINDOW) {
            ++session->face_window_count;
        }
        session->sample_count = count_face_samples(session->face_sample_window);
        return;
    }
    if ((session->stage == SG_STAGE_EYE_CENTER
                || session->stage == SG_STAGE_EYE_LEFT
                || session->stage == SG_STAGE_EYE_RIGHT)
               && sample->eye_valid) {
        session->eye_samples[session->sample_next] = sample->eye;
        session->sample_next = (uint8_t)(
            (session->sample_next + 1U) % SG_SCREENING_STABLE_SAMPLES);
        if (session->sample_count < SG_SCREENING_STABLE_SAMPLES) {
            ++session->sample_count;
        }
    } else if (session->stage == SG_STAGE_TONGUE && sample->tongue_valid) {
        session->tongue_samples[session->sample_next] = sample->tongue;
        session->sample_next = (uint8_t)(
            (session->sample_next + 1U) % SG_SCREENING_STABLE_SAMPLES);
        if (session->sample_count < SG_SCREENING_STABLE_SAMPLES) {
            ++session->sample_count;
        }
    }
}

static bool finish_eye_sequence(sg_screening_session_t *session)
{
    sg_eye_sequence_result_t result = {0};
    if (!sg_eye_score_sequence(
            &session->center_eye, &session->left_eye, &session->right_eye,
            &result)) {
        return false;
    }
    session->eye_result.valid = true;
    session->eye_result.score = result.score;
    session->eye_result.signed_value = result.binocular_difference;
    session->eye_result.quality = result.quality;
    return true;
}

static bool complete_stage(sg_screening_session_t *session, int64_t now_us)
{
    switch (session->stage) {
    case SG_STAGE_FACE:
        enter_stage(session, SG_STAGE_EYE_CENTER, now_us);
        return true;
    case SG_STAGE_EYE_CENTER:
        session->center_eye = median_eye(session->eye_samples);
        enter_stage(session, SG_STAGE_EYE_LEFT, now_us);
        return true;
    case SG_STAGE_EYE_LEFT:
        session->left_eye = median_eye(session->eye_samples);
        enter_stage(session, SG_STAGE_EYE_RIGHT, now_us);
        return true;
    case SG_STAGE_EYE_RIGHT:
        session->right_eye = median_eye(session->eye_samples);
        if (!finish_eye_sequence(session)) {
            enter_stage(session, SG_STAGE_ERROR, now_us);
            return false;
        }
        enter_stage(session, SG_STAGE_TONGUE, now_us);
        return true;
    case SG_STAGE_TONGUE: {
        const sg_tongue_measurement_t result = median_tongue(session->tongue_samples);
        session->tongue_result.valid = true;
        session->tongue_result.score = result.score;
        session->tongue_result.signed_value = result.signed_offset;
        session->tongue_result.quality = result.quality;
        enter_stage(session, SG_STAGE_DONE, now_us);
        return true;
    }
    default:
        return false;
    }
}

void sg_screening_session_update(
    sg_screening_session_t *session,
    const sg_screening_sample_t *sample,
    int64_t now_us)
{
    if (session == NULL || sample == NULL || now_us <= 0) return;
    const int64_t duration = stage_duration(session->stage);
    if (duration == 0) return;
    const int64_t elapsed = now_us - session->stage_started_us;
    const int64_t deadline = session->stage == SG_STAGE_FACE
        ? SG_FACE_DEADLINE_US : duration + SG_STAGE_TIMEOUT_GRACE_US;
    if (elapsed > deadline) {
        enter_stage(session, SG_STAGE_ERROR, now_us);
        return;
    }
    if (elapsed >= SG_STAGE_SETTLE_US) {
        add_sample(session, sample);
    }
    const uint8_t required_samples = session->stage == SG_STAGE_FACE
        ? SG_SCREENING_FACE_REQUIRED_SAMPLES : SG_SCREENING_STABLE_SAMPLES;
    const bool face_ready_to_advance = session->stage == SG_STAGE_FACE
        && elapsed >= SG_STAGE_SETTLE_US
        && session->sample_count >= required_samples;
    const bool timed_stage_ready = session->stage != SG_STAGE_FACE
        && elapsed >= duration
        && session->sample_count >= required_samples;
    if (face_ready_to_advance || timed_stage_ready) {
        (void)complete_stage(session, now_us);
    }
}

sg_screening_stage_t sg_screening_session_stage(
    const sg_screening_session_t *session)
{
    return session == NULL ? SG_STAGE_IDLE : session->stage;
}

uint8_t sg_screening_session_progress(
    const sg_screening_session_t *session, int64_t now_us)
{
    if (session == NULL) return 0;
    if (session->stage == SG_STAGE_DONE) return 100;
    const int64_t duration = stage_duration(session->stage);
    if (duration <= 0 || now_us <= session->stage_started_us) return 0;
    const int64_t progress = (now_us - session->stage_started_us) * 100 / duration;
    return (uint8_t)(progress > 100 ? 100 : progress);
}

static bool copy_result(
    const sg_camera_modal_metrics_t *source, sg_camera_modal_metrics_t *out)
{
    if (out == NULL) return false;
    memset(out, 0, sizeof(*out));
    if (source == NULL || !source->valid) return false;
    *out = *source;
    return true;
}

bool sg_screening_session_eye_result(
    const sg_screening_session_t *session, sg_camera_modal_metrics_t *out)
{
    return copy_result(session == NULL ? NULL : &session->eye_result, out);
}

bool sg_screening_session_tongue_result(
    const sg_screening_session_t *session, sg_camera_modal_metrics_t *out)
{
    return copy_result(session == NULL ? NULL : &session->tongue_result, out);
}
