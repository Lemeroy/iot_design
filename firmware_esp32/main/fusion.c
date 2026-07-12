/**
 * @file fusion.c
 * @brief 五模态融合实现. 与 host_pc/stroke_host/fusion/fusion.py 位对位一致.
 */
#include "fusion.h"
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "app_config.h"

/* ---- 与 Python fusion.py 一致的常量 ---- */
#define W_FACE     0.35f
#define W_SPEECH   0.25f
#define W_TONGUE   0.20f
#define W_EYE      0.12f
#define W_CSI      0.08f

#define FINAL_DANGER_MAX     40
#define FINAL_WARNING_MAX    70

#define SPEECH_P_DANGER_MAX   0.4f
#define EYE_WARNING_MAX       30
#define CSI_WARNING_MAX       30

#define MIN_AVAIL_WEIGHT_SUM  0.50f

static int add_reason(sg_fusion_out_t *o, const char *fmt, ...)
{
    if (o->n_reasons >= SG_FUSION_MAX_REASONS) return -1;
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(o->reasons[o->n_reasons], SG_FUSION_REASON_LEN, fmt, ap);
    va_end(ap);
    o->n_reasons++;
    return 0;
}

const char *sg_fusion_level_name(sg_level_t lv)
{
    switch (lv) {
        case SG_LEVEL_NORMAL:  return "normal";
        case SG_LEVEL_WARNING: return "warning";
        case SG_LEVEL_DANGER:  return "danger";
        default:               return "insufficient";
    }
}

/* 用可用集合的权重之和归一化 */
static float pick_norm_weight(bool avail, float raw, float sum_avail)
{
    if (!avail || sum_avail <= 1e-6f) return 0.0f;
    return raw / sum_avail;
}

void sg_fusion_compute(const sg_scores_in_t *in,
                       int csi_from_s3,
                       sg_fusion_out_t *out)
{
    memset(out, 0, sizeof(*out));
    out->seq = in ? in->seq : 0;

    if (!in) {
        out->level = SG_LEVEL_INSUFFICIENT;
        add_reason(out, "no input");
        return;
    }

    /* 1. 判断可用 & 用 S3 自产 CSI 回填 */
    int8_t face   = in->face;
    int8_t speech = in->speech;
    int8_t tongue = in->tongue;
    int8_t eye    = in->eye;
    int8_t csi    = (in->csi >= 0) ? in->csi
                                   : ((csi_from_s3 >= 0 && csi_from_s3 <= 100)
                                       ? (int8_t)csi_from_s3 : (int8_t)-1);

    bool a_face   = (face   >= 0 && face   <= 100);
    bool a_speech = (speech >= 0 && speech <= 100);
    bool a_tongue = (tongue >= 0 && tongue <= 100);
    bool a_eye    = (eye    >= 0 && eye    <= 100);
    bool a_csi    = (csi    >= 0 && csi    <= 100);

    float sum_w = (a_face   ? W_FACE   : 0.0f)
                + (a_speech ? W_SPEECH : 0.0f)
                + (a_tongue ? W_TONGUE : 0.0f)
                + (a_eye    ? W_EYE    : 0.0f)
                + (a_csi    ? W_CSI    : 0.0f);

    if (sum_w < 1e-6f) {
        out->level = SG_LEVEL_INSUFFICIENT;
        add_reason(out, "no modality available");
        return;
    }
    if (sum_w < MIN_AVAIL_WEIGHT_SUM) {
        out->level = SG_LEVEL_INSUFFICIENT;
        add_reason(out, "avail weight sum %.2f < %.2f",
                   sum_w, (double)MIN_AVAIL_WEIGHT_SUM);
        /* 仍然填充权重以便观察 */
        out->w_face   = pick_norm_weight(a_face,   W_FACE,   sum_w);
        out->w_speech = pick_norm_weight(a_speech, W_SPEECH, sum_w);
        out->w_tongue = pick_norm_weight(a_tongue, W_TONGUE, sum_w);
        out->w_eye    = pick_norm_weight(a_eye,    W_EYE,    sum_w);
        out->w_csi    = pick_norm_weight(a_csi,    W_CSI,    sum_w);
        return;
    }

    /* 2. 归一化权重 + 加权 */
    out->w_face   = pick_norm_weight(a_face,   W_FACE,   sum_w);
    out->w_speech = pick_norm_weight(a_speech, W_SPEECH, sum_w);
    out->w_tongue = pick_norm_weight(a_tongue, W_TONGUE, sum_w);
    out->w_eye    = pick_norm_weight(a_eye,    W_EYE,    sum_w);
    out->w_csi    = pick_norm_weight(a_csi,    W_CSI,    sum_w);

    out->contrib_face   = a_face   ? out->w_face   * (float)face   : 0.0f;
    out->contrib_speech = a_speech ? out->w_speech * (float)speech : 0.0f;
    out->contrib_tongue = a_tongue ? out->w_tongue * (float)tongue : 0.0f;
    out->contrib_eye    = a_eye    ? out->w_eye    * (float)eye    : 0.0f;
    out->contrib_csi    = a_csi    ? out->w_csi    * (float)csi    : 0.0f;

    float final_f = out->contrib_face + out->contrib_speech + out->contrib_tongue
                  + out->contrib_eye  + out->contrib_csi;
    if (final_f < 0.0f)   final_f = 0.0f;
    if (final_f > 100.0f) final_f = 100.0f;
    out->final = (int32_t)(final_f + 0.5f);

    /* 3. 单项否决 (danger) */
    if (a_face) {
        if (face <= SG_FACE_DANGER_MAX) {
            out->veto_face = 1;
            add_reason(out, "veto: F=%d <= %d", face, SG_FACE_DANGER_MAX);
        } else if (!isnan(in->face_theta_deg)
                   && in->face_theta_deg >= SG_FACE_MOUTH_DEG_DANGER) {
            out->veto_face = 1;
            add_reason(out, "veto: mouth_angle=%.1fdeg >= %.1fdeg",
                       (double)in->face_theta_deg,
                       (double)SG_FACE_MOUTH_DEG_DANGER);
        }
    }
    if (a_speech && speech <= SG_SPEECH_DANGER_MAX) {
        if (!isnan(in->speech_p_clear)
            && in->speech_p_clear < SPEECH_P_DANGER_MAX) {
            out->veto_speech = 1;
            add_reason(out, "veto: S=%d <= %d & p_clear=%.2f < %.2f",
                       speech, SG_SPEECH_DANGER_MAX,
                       (double)in->speech_p_clear,
                       (double)SPEECH_P_DANGER_MAX);
        }
    }

    /* 4. 分级 */
    sg_level_t lv;
    if (out->veto_face || out->veto_speech) {
        lv = SG_LEVEL_DANGER;
        add_reason(out, "level=danger by veto");
    } else if (out->final < FINAL_DANGER_MAX) {
        lv = SG_LEVEL_DANGER;
        add_reason(out, "level=danger by final=%ld < %d",
                   (long)out->final, FINAL_DANGER_MAX);
    } else if (out->final < FINAL_WARNING_MAX) {
        lv = SG_LEVEL_WARNING;
        add_reason(out, "level=warning by %d <= final=%ld < %d",
                   FINAL_DANGER_MAX, (long)out->final, FINAL_WARNING_MAX);
    } else {
        lv = SG_LEVEL_NORMAL;
    }

    /* 单项提级到 warning */
    if (lv == SG_LEVEL_NORMAL && a_eye && eye < EYE_WARNING_MAX) {
        lv = SG_LEVEL_WARNING;
        add_reason(out, "upgrade to warning: E=%d < %d",
                   eye, EYE_WARNING_MAX);
    }
    if (lv == SG_LEVEL_NORMAL && a_csi && csi < CSI_WARNING_MAX) {
        lv = SG_LEVEL_WARNING;
        add_reason(out, "upgrade to warning: B=%d < %d",
                   csi, CSI_WARNING_MAX);
    }

    out->level = lv;
}
