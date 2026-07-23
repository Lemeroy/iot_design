#include "speech_screening.h"

#include <limits.h>
#include <math.h>
#include <string.h>

#define SG_SPEECH_MIN_VALID_FRAMES 55U
#define SG_SPEECH_MIN_VOICED_FRAMES 45U
#define SG_SPEECH_MAX_CLIPPED_RATIO 0.05f
#define SG_SPEECH_VAD_RATIO 1.60f
#define SG_SPEECH_VAD_MARGIN 5.0f
#define SG_SPEECH_SAMPLE_RATE 16000.0f
#define SG_SPEECH_MIN_ZCR 0.010f
#define SG_SPEECH_MAX_ZCR 0.280f
#define SG_SPEECH_MIN_BAND_BALANCE 0.005f

static float clamp01(float value)
{
    if (value < 0.0f) return 0.0f;
    if (value > 1.0f) return 1.0f;
    return value;
}

static float maximum(float a, float b)
{
    return a > b ? a : b;
}

static double goertzel_power(const int16_t *samples, size_t count,
                             float frequency, float mean)
{
    const float omega = 2.0f * (float)M_PI * frequency
        / SG_SPEECH_SAMPLE_RATE;
    const float coefficient = 2.0f * cosf(omega);
    double previous = 0.0;
    double previous_two = 0.0;
    for (size_t i = 0; i < count; ++i) {
        const double centered = (double)samples[i] - (double)mean;
        const double current = centered
            + (double)coefficient * previous - previous_two;
        previous_two = previous;
        previous = current;
    }
    double power = previous_two * previous_two + previous * previous
        - (double)coefficient * previous * previous_two;
    return power > 0.0 ? power : 0.0;
}

static void finish_session(sg_speech_context_t *context)
{
    sg_speech_result_t *result = &context->result;
    const float clipped_ratio = context->total_samples == 0U ? 0.0f
        : (float)context->clipped_samples / (float)context->total_samples;
    result->available = false;
    result->score = 0U;
    result->p_clear = 0.0f;
    result->state = SG_SPEECH_RETRY;

    if (clipped_ratio > SG_SPEECH_MAX_CLIPPED_RATIO) {
        result->reason = SG_SPEECH_REASON_CLIPPED;
        return;
    }
    if (result->voiced_frames == 0U) {
        result->reason = SG_SPEECH_REASON_NO_VOICE;
        return;
    }
    if (result->valid_frames < SG_SPEECH_MIN_VALID_FRAMES
        || result->voiced_frames < SG_SPEECH_MIN_VOICED_FRAMES) {
        result->reason = SG_SPEECH_REASON_TOO_SHORT;
        return;
    }

    const float voiced = (float)result->voiced_frames;
    const float voiced_ratio = voiced / (float)(result->valid_frames
        - SG_SPEECH_NOISE_FRAMES);
    const float mean_rms = (float)(context->voiced_rms_sum / voiced);
    const float rms_variance = maximum(0.0f,
        (float)(context->voiced_rms_sq_sum / voiced) - mean_rms * mean_rms);
    const float rms_cv = sqrtf(rms_variance) / maximum(mean_rms, 1.0f);
    if (mean_rms < maximum(context->noise_rms * 1.35f,
                           context->noise_rms + 2.0f)) {
        result->reason = SG_SPEECH_REASON_TOO_QUIET;
        return;
    }

    const float continuity = clamp01(
        (float)context->longest_voice_run / voiced);
    const float voiced_quality = clamp01(voiced_ratio / 0.35f);
    const float dynamics = clamp01(rms_cv / 0.30f);
    const float mean_zcr = (float)(context->zcr_sum / voiced);
    const float zcr_quality = clamp01(1.0f
        - fabsf(mean_zcr - 0.07f) / 0.12f);
    const double band_total = context->band_sum[0] + context->band_sum[1]
        + context->band_sum[2];
    float band_balance = 0.0f;
    if (band_total > 1.0) {
        double largest = context->band_sum[0];
        if (context->band_sum[1] > largest) largest = context->band_sum[1];
        if (context->band_sum[2] > largest) largest = context->band_sum[2];
        band_balance = clamp01((float)(1.0 - largest / band_total) / 0.55f);
    }
    if (mean_zcr < SG_SPEECH_MIN_ZCR || mean_zcr > SG_SPEECH_MAX_ZCR
        || band_balance < SG_SPEECH_MIN_BAND_BALANCE) {
        result->reason = SG_SPEECH_REASON_NON_SPEECH;
        return;
    }

    const float snr_quality = clamp01(
        (mean_rms / maximum(context->noise_rms, 1.0f) - 1.2f) / 3.8f);
    const float raw_clear = clamp01(0.30f * continuity
        + 0.25f * voiced_quality
        + 0.15f * dynamics
        + 0.10f * zcr_quality
        + 0.10f * band_balance
        + 0.10f * snr_quality);
    const float p_clear = clamp01(powf(raw_clear, 1.15f));
    result->p_clear = p_clear;
    result->score = (uint8_t)lroundf(100.0f * p_clear);
    result->reason = SG_SPEECH_REASON_NONE;
    result->available = true;
    result->state = SG_SPEECH_COMPLETE;
}

void sg_speech_screening_init(sg_speech_context_t *context)
{
    if (context == NULL) return;
    memset(context, 0, sizeof(*context));
    context->result.state = SG_SPEECH_IDLE;
}

void sg_speech_screening_start(sg_speech_context_t *context)
{
    sg_speech_screening_init(context);
    if (context != NULL) context->result.state = SG_SPEECH_LISTENING;
}

void sg_speech_screening_cancel(sg_speech_context_t *context)
{
    sg_speech_screening_init(context);
}

void sg_speech_screening_process(sg_speech_context_t *context,
                                 const int16_t *samples, size_t count)
{
    if (context == NULL || samples == NULL
        || count != SG_SPEECH_FRAME_SAMPLES
        || context->result.state != SG_SPEECH_LISTENING) {
        return;
    }

    int64_t sum = 0;
    for (size_t i = 0; i < count; ++i) sum += samples[i];
    const float mean = (float)sum / (float)count;
    double energy = 0.0;
    uint32_t clipped = 0U;
    uint32_t crossings = 0U;
    int32_t peak = 0;
    int32_t previous = (int32_t)((float)samples[0] - mean);
    for (size_t i = 0; i < count; ++i) {
        int32_t centered = (int32_t)((float)samples[i] - mean);
        int32_t magnitude = centered == INT16_MIN ? 32768
            : (centered < 0 ? -centered : centered);
        if (magnitude > peak) peak = magnitude;
        if (samples[i] >= 32760 || samples[i] <= -32760) ++clipped;
        energy += (double)centered * (double)centered;
        if (i > 0U && ((previous < 0 && centered >= 0)
                       || (previous >= 0 && centered < 0))) {
            ++crossings;
        }
        previous = centered;
    }

    const float rms = sqrtf((float)(energy / (double)count));
    sg_speech_result_t *result = &context->result;
    ++result->valid_frames;
    context->clipped_samples += clipped;
    context->total_samples += (uint32_t)count;
    if (rms > result->rms) result->rms = rms;
    if (peak > result->peak) {
        result->peak = (int16_t)(peak > INT16_MAX ? INT16_MAX : peak);
    }

    if (result->valid_frames <= SG_SPEECH_NOISE_FRAMES) {
        context->noise_rms_sum += rms;
        context->noise_rms = maximum(
            context->noise_rms_sum / (float)result->valid_frames, 1.0f);
    } else {
        const float threshold = maximum(context->noise_rms * SG_SPEECH_VAD_RATIO,
                                        context->noise_rms + SG_SPEECH_VAD_MARGIN);
        if (rms >= threshold) {
            ++result->voiced_frames;
            ++context->current_voice_run;
            if (context->current_voice_run > context->longest_voice_run) {
                context->longest_voice_run = context->current_voice_run;
            }
            context->voiced_rms_sum += rms;
            context->voiced_rms_sq_sum += (double)rms * (double)rms;
            context->zcr_sum += (double)crossings / (double)(count - 1U);
            context->band_sum[0] += goertzel_power(samples, count, 300.0f, mean);
            context->band_sum[1] += goertzel_power(samples, count, 1000.0f, mean);
            context->band_sum[2] += goertzel_power(samples, count, 3000.0f, mean);
        } else {
            context->current_voice_run = 0U;
        }
    }

    if (result->valid_frames >= SG_SPEECH_MAX_FRAMES) finish_session(context);
}

void sg_speech_screening_fail(sg_speech_context_t *context,
                              sg_speech_reason_t reason)
{
    if (context == NULL || context->result.state != SG_SPEECH_LISTENING
        || reason == SG_SPEECH_REASON_NONE) {
        return;
    }
    context->result.available = false;
    context->result.score = 0U;
    context->result.p_clear = 0.0f;
    context->result.reason = reason;
    context->result.state = SG_SPEECH_RETRY;
}

void sg_speech_screening_snapshot(const sg_speech_context_t *context,
                                  sg_speech_result_t *result)
{
    if (context == NULL || result == NULL) return;
    *result = context->result;
}
