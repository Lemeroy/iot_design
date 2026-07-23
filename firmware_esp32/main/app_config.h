/**
 * @file app_config.h
 * @brief 卒中卫士 M1a 全局配置宏
 */
#pragma once

/* ==== 固件版本 ==== */
#define SG_FW_VERSION           "e1-0.5.2"

/* ==== USB-CDC 帧协议 v1 ==== */
#define SG_FRAME_MAGIC0         0xA5
#define SG_FRAME_MAGIC1         0x5A
#define SG_FRAME_VER            0x01

#define SG_FRAME_TYPE_HEARTBEAT 0x01
#define SG_FRAME_TYPE_DATA      0x02  /* M1b 起用 */
#define SG_FRAME_TYPE_SCORES    0x03  /* PC -> S3: 感知分数 */
#define SG_FRAME_TYPE_FUSION    0x04  /* S3 -> PC: 融合结果 */
#define SG_FRAME_TYPE_LOG       0xF0

#define SG_FRAME_HEADER_LEN     6     /* magic(2)+ver(1)+type(1)+len(2) */
#define SG_FRAME_CRC_LEN        2
#define SG_FRAME_MAX_PAYLOAD    1024  /* fusion 帧 reasons 会大一些 */

/* ==== CSI 参数 (v0.3: RuView 借鉴, 三特征融合) ==== */
#define SG_CSI_WINDOW_SEC       5
#define SG_CSI_WINDOW_MAX       55    /* 实测约 11 Hz，对应约 5 秒滑窗 */
#define SG_CSI_MIN_SAMPLES      16    /* 至少这么多样本才出分 (~1.5s @ 10Hz) */
#define SG_CSI_UPDATE_EVERY     5     /* 每 N 个新包更新一次分 */

/* 三特征融合权重 (总和 = 1.0), 来源: RuView README 信号处理章节 */
#define SG_CSI_W_AMP_CV         0.50f /* 幅度变异系数 (静止时 CV 小) */
#define SG_CSI_W_PHASE_VAR      0.00f /* 单子载波绝对相位实测不稳定，仅保留诊断 */
#define SG_CSI_W_MOTION_BAND    0.50f /* 运动带能量 (差分平方和, 反映动作剧烈度) */

/* 打分参数, 待实测标定 (M6);
 * v0.3.3: 相位改用圆方差 cvar in [0,1]. 静止 cvar~0.1, 动作 cvar~0.6 */
#define SG_CSI_K_AMP_CV         400.0f  /* 2026-07-23 COM3 初赛实测标定，待 M6 扩样本 */
#define SG_CSI_K_PHASE_VAR      100.0f  /* 静止 cvar=0.10 -> 90; 动作 0.5 -> 50 */
#define SG_CSI_K_MOTION         320.0f  /* 2026-07-23 COM3 初赛实测标定，待 M6 扩样本 */

/* ==== CSI Ping keep-alive (RuView 建议: 保证 CSI 包流量) ==== */
#define SG_CSI_PING_INTERVAL_MS 100   /* 10 Hz ICMP ping 网关, CSI 采样率主要靠这个 */
#define SG_CSI_PING_STACK       4096
#define SG_CSI_PING_PRIO        3
#define SG_CSI_PING_CORE        0

/* ==== 任务栈/优先级 ==== */
#define SG_TASK_HEARTBEAT_STACK 3072
#define SG_TASK_HEARTBEAT_PRIO  4
#define SG_TASK_HEARTBEAT_CORE  1

#define SG_TASK_FRAME_STACK     4096
#define SG_TASK_FRAME_PRIO      4
#define SG_TASK_FRAME_CORE      1
#define SG_FRAME_PERIOD_MS      1000  /* synthetic M1 frame, replace after sensors arrive */

#define SG_TASK_CSI_STACK       4096
#define SG_TASK_CSI_PRIO        5
#define SG_TASK_CSI_CORE        1

#define SG_TASK_CDC_TX_STACK    4096
#define SG_TASK_CDC_TX_PRIO     6
#define SG_TASK_CDC_TX_CORE     1

/* ==== 队列 ==== */
#define SG_CDC_TX_QUEUE_LEN     8
#define SG_CSI_RAW_QUEUE_LEN    32
#define SG_SCORES_RX_QUEUE_LEN  8

/* ==== 融合任务 ==== */
#define SG_TASK_FUSION_STACK    4096
#define SG_TASK_FUSION_PRIO     6
#define SG_TASK_FUSION_CORE     0
#define SG_TASK_FUSION_PERIOD_MS 1000
#define SG_SCORE_STALE_MS        5000
#define SG_MQTT_PUBLISH_PERIOD_MS 10000
#define SG_ADVICE_MAX_AGE_SEC       300

/* Medical screening thresholds are fixed and exposed read-only. */
#define SG_FACE_DANGER_MAX          30
#define SG_FACE_MOUTH_DEG_DANGER    20
#define SG_SPEECH_DANGER_MAX        35

#define SG_TASK_ADVICE_STACK    4096
#define SG_TASK_ADVICE_PRIO     5
#define SG_TASK_ADVICE_CORE     0

#define SG_CAMERA_POLL_PERIOD_MS 500
#define SG_TASK_CAMERA_STACK     4096
#define SG_TASK_CAMERA_PRIO      5
#define SG_TASK_CAMERA_CORE      0

#define SG_TASK_AUDIO_STACK      4096
#define SG_TASK_AUDIO_PRIO       5
#define SG_TASK_AUDIO_CORE       1

/* ==== CDC RX 任务 (JSON 帧解析) ==== */
#define SG_TASK_CDC_RX_STACK    4096
#define SG_TASK_CDC_RX_PRIO     5
#define SG_TASK_CDC_RX_CORE     0

/* ==== 启动延迟: USB 枚举稳定后再启 WiFi ==== */
#define SG_USB_TO_WIFI_DELAY_MS 2000
