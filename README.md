# 卒中卫士 · StrokeGuard

基于 ESP32-S3 多模态感知的脑卒中风险提示智能健康镜。

> 当前权威架构：ESP32-S3 独立完成感知、融合、告警和云端通信；PC 仅作同局域网监控与标定工具。详细设计见 [独立镜端架构规格](docs/superpowers/specs/2026-07-11-standalone-edge-mirror-design.md)。

## 架构

```text
GC2145 + INMP441 + Wi-Fi CSI
              │
              v
┌────────────────────────────────────┐
│ ESP32-S3-WROOM-1 N16R8 独立镜端    │
│ F/S/T/E/B 边缘评分 · 确定性融合     │
│ TFT/语音/LED/蜂鸣器 · 离线告警      │
└──────────────┬─────────────────────┘
               │ MQTT：仅数值评分/建议文本
               v
┌────────────────────────────────────┐
│ EMQX · InfluxDB · FastAPI · 豆包   │
└────────────────────────────────────┘

可选 PC ──同局域网 HTTP/WebSocket──> 状态监控、受限配置、人工校准
```

- 三类物理感知来源：摄像头、麦克风、Wi-Fi CSI。
- 五个评分模态：面部 F、言语 S、舌偏辅助 T、眼动 E、稳定性 B。
- 原始音视频只在镜端处理，绝不上云。局域网原始校准流默认关闭，必须经认证、物理按键授权、可见提示并自动超时。
- 云端大模型只生成建议文本，不能修改或取消镜端确定性告警。
- 产品用于风险提示和就医提醒，不是医疗诊断设备。
- Arm 因镜子视野限制不单独测量；如需补全，应另配可穿戴或外部设备。

## 目录

```text
strokeguard/
├── firmware_esp32/  # ESP-IDF 5.5.3 固件；当前含 CSI、USB、融合和外设脚手架
├── host_pc/         # PyQt5 管理端及 PC 算法对照原型，不是运行依赖
├── cloud/           # EMQX、InfluxDB、FastAPI、大模型和微信小程序
├── docs/            # 架构规格、接线和实施计划
└── scripts/         # 本地与云端部署/联调脚本
```

## 核心契约

### S3 到云端

```text
Topic: strokeguard/<device_id>/uplink
```

```json
{
  "schema_version": 1,
  "seq": 0,
  "scores": {"face": 0, "speech": 0, "tongue": 0, "eye": 0, "csi": 0, "final": 0},
  "level": "normal|warning|danger|insufficient",
  "profile": {"age": 0, "conditions": []},
  "reasons": [],
  "veto_by": [],
  "device_id": "sg-0001",
  "ts": 0
}
```

禁止字段：原始 JPEG、音频、MFCC、关键点和其他可还原生物特征的数据。

### 云端到 S3

```text
Topic: strokeguard/<device_id>/downlink
```

```json
{"schema_version":1,"level":"warning","advice_text":"给本人或家属的安全建议文本","ts":0,"source":"doubao"}
```

### PC 局域网管理

```text
GET  /api/v1/status
GET  /api/v1/config
PUT  /api/v1/config
POST /api/v1/calibration/start
POST /api/v1/calibration/stop
POST /api/v1/update/model
POST /api/v1/update/firmware
WS   /api/v1/telemetry
WS   /api/v1/calibration
```

模型/固件更新必须经过认证、镜端物理确认、签名校验和失败回滚。发布固件中的融合权重与危险否决阈值不可远程修改。USB-CDC 保留用于烧录、恢复和底层调试，不再承担正常运行时的评分输入。

## 融合规则

```text
final = 0.35 * F + 0.25 * S + 0.20 * T + 0.12 * E + 0.08 * B
```

- `face <= 30` 或口角偏移绝对值 `>= 20°`：`danger`。
- `speech <= 35` 且 `p_clear < 0.4`：`danger`。
- 无否决时：`final >= 70` 为 `normal`，`40 <= final < 70` 为 `warning`，`final < 40` 为 `danger`。
- T 只作辅助，不设置单项否决。可用权重不足时返回 `insufficient`，不得把缺失数据当正常。

阈值是项目实现基线，尚不是经临床验证的诊断阈值；精度、时延和 CSI 标定结果均待真机与合规数据实测。

## 当前状态

| 能力 | 状态 |
| --- | --- |
| CSI 端侧评分、USB 帧协议、S3 融合 C 实现 | 已有原型 |
| PC 五模态算法原型与 PyQt5 UI | 已有，后续转为对照/管理工具 |
| EMQX、InfluxDB、FastAPI、豆包建议链路 | 已部署并完成链路验证 |
| S3 直连 MQTT 与独立离线闭环 | E1 固件已上板；云端联调待 2.4 GHz Wi-Fi 与 VPS 可达性恢复 |
| GC2145/INMP441 边缘模型及训练权重 | 未完成；外设和数据到位后实测 |
| 局域网管理 API 与校准安全机制 | 未完成；E5 交付 |

## 新里程碑

1. `E1`：S3 直连 MQTT、NVS 配置、镜端融合、离线告警和建议下行。
2. `E2`：GC2145 人脸检测、面部对称 F 和口角辅助量。
3. `E3`：INMP441、MFCC、INT8 言语清晰度 S。
4. `E4`：舌偏 T、眼动 E、CSI B、完整融合和镜面交互。
5. `E5`：PC 局域网监控、受限配置、人工授权校准和模型更新。
6. `E6`：训练/量化、TLS、OTA、硬件在环、K 折评测和打包。

## 开发入口

固件环境：ESP32-S3-WROOM-1 N16R8、ESP-IDF v5.5.3、当前串口 `COM3`。

```powershell
cd firmware_esp32
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
idf.py -p COM3 flash monitor
```

PC 测试：

```powershell
cd host_pc
.venv\Scripts\python.exe -m pytest -q
```

外设引脚尚未由实物接线确认，固件 Kconfig 默认使用 `-1` 表示未分配；不要按猜测启用驱动。接线状态见 [wiring.md](docs/wiring.md)。

## 医学免责声明

本设备是家庭健康风险提示工具，不是医疗诊断设备，不能替代医生的临床评估与治疗建议。若出现突发面部歪斜、言语不清、单侧肢体无力、视物异常、平衡障碍或意识改变等症状，无论设备结果如何，都应立即拨打 120，不等待复测或云端建议。
