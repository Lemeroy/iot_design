/**
 * @file fusion.h
 * @brief 五模态融合 + 单项否决 (S3 端, C 移植自 host_pc/stroke_host/fusion/fusion.py)
 *
 * 契约 (Ark, Dr.Chen 会签):
 *   final = 0.35F + 0.35S + 0.08T + 0.14E + 0.08B
 *   缺失模态: 剩余权重按比例归一
 *   可用权重和 < 0.5 -> insufficient
 *   单项否决 (danger): F<=30 或 face_theta>=20°; S<=35 且 p_clear<0.4
 *   单项 warning (提级): B<30；连续 E 仅参与加权，不单项提级
 *   总分级: >=70 normal, [40,70) warning, <40 danger
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef enum {
    SG_LEVEL_INSUFFICIENT = 0,
    SG_LEVEL_NORMAL       = 1,
    SG_LEVEL_WARNING      = 2,
    SG_LEVEL_DANGER       = 3,
} sg_level_t;

/* -1 表示模态不可用 (score < 0 或未测) */
typedef struct {
    int32_t seq;

    int8_t  face;              /* 0-100, -1=NA */
    float   face_theta_deg;    /* 口角偏移绝对值; NaN 或 0 皆视为未测 */

    int8_t  speech;
    float   speech_p_clear;    /* [0,1], NaN=未测 */
    bool    speech_veto_eligible;

    int8_t  tongue;

    int8_t  eye;

    int8_t  csi;               /* 如为 -1, fusion 会用 S3 自产的 CSI 分回填 */
} sg_scores_in_t;

#define SG_FUSION_MAX_REASONS 8
#define SG_FUSION_REASON_LEN  64

typedef struct {
    int32_t     seq;
    int32_t     final;         /* 0-100 */
    sg_level_t  level;
    int32_t     veto_face;     /* 0/1 */
    int32_t     veto_speech;   /* 0/1 */
    /* 加权贡献 (归一化权重 * 分), 便于 PC 侧观察 */
    float       contrib_face;
    float       contrib_speech;
    float       contrib_tongue;
    float       contrib_eye;
    float       contrib_csi;
    float       w_face;
    float       w_speech;
    float       w_tongue;
    float       w_eye;
    float       w_csi;
    /* 结构化理由字符串 */
    int32_t     n_reasons;
    char        reasons[SG_FUSION_MAX_REASONS][SG_FUSION_REASON_LEN];
} sg_fusion_out_t;

/**
 * @brief 计算融合结果 (纯函数, 无副作用).
 * @param in  输入分数 (可含 -1 表示 NA)
 * @param csi_from_s3  S3 自产 CSI 分 (0-100 或 -1); 当 in->csi == -1 时使用
 * @param out 输出融合结果
 */
void sg_fusion_compute(const sg_scores_in_t *in,
                       int csi_from_s3,
                       sg_fusion_out_t *out);

const char *sg_fusion_level_name(sg_level_t lv);
