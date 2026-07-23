/**
 * @file csi_monitor.c
 * @brief CSI 稳定性打分 (B 分)
 *
 * v0.3 三特征融合, 借鉴 https://github.com/ruvnet/RuView (MIT):
 *   - 幅度 CV     : 静止时子载波幅度稳定, CV 小 -> 高分
 *   - 相位方差   : 相位 unwrap 后方差, 不受 AGC 影响 (RuView 亮点)
 *   - 运动带能量 : 相邻样本 L2 差分平方和 -> 动作剧烈度
 *
 * 目标: 端侧 1 Hz 出分, 反映"镜前姿态稳定性" (BE-FAST 里的 B, 平衡辅助).
 */
#include "csi_monitor.h"
#include "app_config.h"
#include "log_tag.h"

#include <math.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_wifi_types.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* 单个 CSI 样本: 幅度 + 相位 (取参考子载波, 保留 wrapped) */
typedef struct {
    float amp;      /* 全部子载波 L2 幅度 */
    float phase;    /* 参考子载波相位, wrapped [-pi, pi] */
} csi_sample_t;

static QueueHandle_t s_csi_q = NULL;
static SemaphoreHandle_t s_score_mtx = NULL;
static volatile int s_score = -1;

/* 滑窗 (环形) */
static csi_sample_t s_win[SG_CSI_WINDOW_MAX];
static size_t s_win_head = 0;
static size_t s_win_cnt  = 0;

/* ---------- CSI 回调: 只做最小拷贝, 严禁 malloc/log ---------- */
static void IRAM_ATTR csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || info->len <= 0) return;

    /* CSI buf: 交错 I/Q, 每个子载波 2 字节 (int8 i, int8 q) */
    int n_sub = info->len / 2;
    if (n_sub <= 0) return;

    /* 全带幅度 (L2) */
    double sq = 0.0;
    const int8_t *p = (const int8_t *)info->buf;
    for (int i = 0; i < n_sub; i++) {
        int8_t I = p[2 * i];
        int8_t Q = p[2 * i + 1];
        sq += (double)I * I + (double)Q * Q;
    }
    float amp = (float)sqrt(sq);

    /* 参考子载波相位: 取 1/4 位置 (避开 DC/边缘/pilot),
     *   LLTF: 64 SC, DC 在 32, DC±1 无效, pilot 在 ±7/±21;
     *   n_sub/4 大约落在 SC ±16 附近, 数据子载波, 相位有意义 */
    int ref = n_sub / 4;
    if (ref < 2) ref = 2;
    int8_t I_ref = p[2 * ref];
    int8_t Q_ref = p[2 * ref + 1];
    /* I/Q 都是 0 时 atan2 返回 0, 会导致方差恒为 0, 直接跳过 */
    float phase;
    if (I_ref == 0 && Q_ref == 0) {
        /* 尝试相邻 SC */
        int alt = ref + 4;
        if (alt < n_sub) {
            I_ref = p[2 * alt];
            Q_ref = p[2 * alt + 1];
        }
    }
    phase = atan2f((float)Q_ref, (float)I_ref);  /* [-pi, pi] */

    csi_sample_t s = { .amp = amp, .phase = phase };

    BaseType_t hpw = pdFALSE;
    xQueueSendFromISR(s_csi_q, &s, &hpw);
    if (hpw) portYIELD_FROM_ISR();
}

/* ---------- 三特征 -> 融合分 ---------- */
static int compute_score(void)
{
    if (s_win_cnt < SG_CSI_MIN_SAMPLES) return -1;

    /* ---- 1) 幅度 CV ---- */
    double mu_a = 0.0;
    for (size_t i = 0; i < s_win_cnt; i++) mu_a += s_win[i].amp;
    mu_a /= s_win_cnt;
    if (mu_a < 1e-6) return -1;
    double var_a = 0.0;
    for (size_t i = 0; i < s_win_cnt; i++) {
        double d = s_win[i].amp - mu_a;
        var_a += d * d;
    }
    double cv = sqrt(var_a / s_win_cnt) / mu_a;
    double s_amp = 100.0 - SG_CSI_K_AMP_CV * cv;
    if (s_amp < 0) s_amp = 0;
    if (s_amp > 100) s_amp = 100;

    /* ---- 2) 圆方差 (circular variance): 1 - |mean(e^{iφ})| in [0,1] ----
     * 静止时相位聚集 -> cvar 接近 0; 动作时相位散开 -> cvar 接近 1.
     * 无需 unwrap, 无 drift 问题. */
    double sum_cos = 0.0, sum_sin = 0.0;
    for (size_t i = 0; i < s_win_cnt; i++) {
        sum_cos += cos(s_win[i].phase);
        sum_sin += sin(s_win[i].phase);
    }
    double R = sqrt(sum_cos * sum_cos + sum_sin * sum_sin) / (double)s_win_cnt;
    double cvar = 1.0 - R;    /* in [0, 1] */
    double s_phase = 100.0 - SG_CSI_K_PHASE_VAR * cvar;
    if (s_phase < 0) s_phase = 0;
    if (s_phase > 100) s_phase = 100;

    /* ---- 3) 运动带能量: 相邻样本差分平方和 / 均值 (归一化) ---- */
    double motion = 0.0;
    for (size_t i = 1; i < s_win_cnt; i++) {
        double d = s_win[i].amp - s_win[i - 1].amp;
        motion += d * d;
    }
    motion = sqrt(motion / (s_win_cnt - 1)) / mu_a;  /* 归一化差分幅度 */
    double s_motion = 100.0 - SG_CSI_K_MOTION * motion;
    if (s_motion < 0) s_motion = 0;
    if (s_motion > 100) s_motion = 100;

    /* ---- 融合 ---- */
    double fused = SG_CSI_W_AMP_CV     * s_amp
                 + SG_CSI_W_PHASE_VAR  * s_phase
                 + SG_CSI_W_MOTION_BAND* s_motion;
    int score = (int)(fused + 0.5);
    if (score < 0) score = 0;
    if (score > 100) score = 100;

    /* 打分日志 (5s 一次, 别刷屏) */
    static TickType_t last_log = 0;
    TickType_t now = xTaskGetTickCount();
    if (now - last_log > pdMS_TO_TICKS(5000)) {
        ESP_LOGI(SG_TAG_CSI,
                 "win=%u cv=%.3f cvar=%.3f mot=%.3f => A=%.0f P=%.0f M=%.0f = %d",
                 (unsigned)s_win_cnt, cv, cvar, motion,
                 s_amp, s_phase, s_motion, score);
        last_log = now;
    }
    return score;
}

/* ---------- 消费任务 ---------- */
static void task_csi(void *arg)
{
    csi_sample_t s;
    TickType_t last_diag = xTaskGetTickCount();
    uint32_t pkt_cnt = 0;
    uint32_t pkt_cnt_last = 0;

    while (1) {
        if (xQueueReceive(s_csi_q, &s, pdMS_TO_TICKS(1000)) != pdTRUE) {
            /* 5s 静默诊断: 让我们知道回调有没有触发 */
            TickType_t now = xTaskGetTickCount();
            if (now - last_diag > pdMS_TO_TICKS(5000)) {
                ESP_LOGW(SG_TAG_CSI, "diag: total_pkt=%lu delta=%lu score=%d win=%u",
                         (unsigned long)pkt_cnt,
                         (unsigned long)(pkt_cnt - pkt_cnt_last),
                         s_score, (unsigned)s_win_cnt);
                pkt_cnt_last = pkt_cnt;
                last_diag = now;
            }
            continue;
        }
        pkt_cnt++;

        /* 直接存 wrapped 相位, compute_score 里用圆统计 */
        s_win[s_win_head] = s;
        s_win_head = (s_win_head + 1) % SG_CSI_WINDOW_MAX;
        if (s_win_cnt < SG_CSI_WINDOW_MAX) s_win_cnt++;

        if ((pkt_cnt % SG_CSI_UPDATE_EVERY) != 0) continue;

        int sc = compute_score();
        if (sc < 0) continue;
        xSemaphoreTake(s_score_mtx, portMAX_DELAY);
        s_score = sc;
        xSemaphoreGive(s_score_mtx);
    }
}

esp_err_t sg_csi_start(void)
{
    s_csi_q = xQueueCreate(SG_CSI_RAW_QUEUE_LEN, sizeof(csi_sample_t));
    if (!s_csi_q) return ESP_ERR_NO_MEM;

    s_score_mtx = xSemaphoreCreateMutex();
    if (!s_score_mtx) return ESP_ERR_NO_MEM;

    wifi_csi_config_t csi_cfg = {
        .lltf_en          = true,
        .htltf_en         = true,
        .stbc_htltf2_en   = true,
        .ltf_merge_en     = true,
        .channel_filter_en= true,
        .manu_scale       = false,
        .shift            = 0,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(&csi_rx_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));

    xTaskCreatePinnedToCore(task_csi, "csi",
                            SG_TASK_CSI_STACK, NULL,
                            SG_TASK_CSI_PRIO, NULL,
                            SG_TASK_CSI_CORE);

    ESP_LOGI(SG_TAG_CSI,
             "csi started (v0.4 5s window: amp_cv+motion; phase diagnostic only)");
    return ESP_OK;
}

int sg_csi_get_score(void)
{
    if (!s_score_mtx) return -1;
    int v;
    xSemaphoreTake(s_score_mtx, portMAX_DELAY);
    v = s_score;
    xSemaphoreGive(s_score_mtx);
    return v;
}
