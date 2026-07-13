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

可选 PC ──同局域网 HTTP──> 状态监控、受限档案配置
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
GET  /api/v1/config
PUT  /api/v1/config
```

当前接口只允许读取完整配置和更新 `profile`，采用 Bearer Token、固定请求上限和 revision 乐观锁。Token 存在镜端 NVS 与 PC 系统凭据库，不进入 YAML。设备 ID、网络、MQTT、融合权重、危险阈值和否决规则均不可通过该接口修改。详见 [PC 配置手册](docs/pc-yaml-config.md)。

校准、模型更新和 OTA 仍是规划项；后续实现必须经过认证、镜端物理确认、签名校验和失败回滚。USB-CDC 只用于烧录、恢复和调试遥测，不承担正常运行时的评分输入。

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
| PC 五模态算法原型与 PyQt5 UI | 已有；当前作为可选监控与 YAML 管理工具 |
| EMQX、InfluxDB、FastAPI、豆包建议链路 | 已部署并完成链路验证 |
| S3 直连 MQTT 与独立离线闭环 | E1 固件已上板；离线融合、CSI、数值上行、InfluxDB 落库及大模型建议下行已完成真机验证 |
| GC2145/INMP441 边缘模型及训练权重 | 未完成；外设和数据到位后实测 |
| 局域网档案管理 API | GET/PUT、鉴权、revision 冲突与 PC Keyring 已完成 |
| 校准、签名更新与 OTA | 未完成；E5/E6 交付 |

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

### 给另一块 ESP32-S3 烧录固件

以下流程只适用于与当前开发板一致的 **ESP32-S3-WROOM-1 N16R8（16 MB Flash、8 MB OPI PSRAM）**。其他 S3 模组的 Flash/PSRAM 配置可能不同，不要直接照搬镜像。

1. 打开 `C:\Users\Administrator\Desktop\IDF_v5.5.3_Powershell.lnk`，进入固件目录并确认新板串口：

   ```powershell
   cd F:\iot_design\firmware_esp32
   Get-CimInstance Win32_SerialPort | Select-Object DeviceID,Name
   idf.py --version
   ```

2. 为新设备配置独立参数：

   ```powershell
   idf.py set-target esp32s3
   idf.py menuconfig
   ```

   在 `StrokeGuard M1a/M1b Config` 中设置 2.4 GHz Wi-Fi、MQTT 地址/账号及唯一 `Device ID`（例如 `sg-0002`）。多块镜子不能共用同一个 `Device ID`，否则网页监控和 MQTT 主题会互相覆盖。不要把生成的 `sdkconfig` 或任何密码提交到 Git。

3. 将下面的 `COM5` 替换为新板实际串口，清除旧 NVS 后构建、烧录并观察启动日志：

   ```powershell
   idf.py -p COM5 erase-flash
   idf.py build
   idf.py -p COM5 flash monitor
   ```

   `erase-flash` 会清除该板原有固件和 NVS，仅对确认可覆盖的目标板执行。退出串口监视按 `Ctrl+]`。

4. 验收：日志应出现 Wi-Fi `GOT_IP`、CSI 启动和 MQTT 连接/上行；随后通过外网演示页连接该板的 `Device ID`，确认 CSI、最终状态和大模型建议能够同步。

若多块板使用**完全相同**的配置，可先执行一次 `idf.py build`，之后逐块更换串口并运行 `idf.py -p COMx flash`，无需重复编译。但正式多设备部署仍应逐块设置唯一 `Device ID` 后重新构建、烧录。详细故障处理见 [固件 README](firmware_esp32/README.md)。

PC 测试：

```powershell
cd host_pc
.venv\Scripts\python.exe -m pytest -q
```

外设引脚尚未由实物接线确认，固件 Kconfig 默认使用 `-1` 表示未分配；不要按猜测启用驱动。接线状态见 [wiring.md](docs/wiring.md)。

## 初赛桌面演示程序

`dist/StrokeGuard-Demo.exe` 默认连接 VPS 上的真实设备 `sg-0001`，只显示实时 F/S/T/E/CSI、镜端融合状态和最新豆包建议。它不提供模拟数据；云端不可达、登录失效、设备离线和模态未接入会分别显示。数据不足时融合评分显示“未形成”，不会把无效的 `0` 误显示为危险评分。

“设备维护”页提供：

- 部署 YAML 编辑与严格校验；
- `device_id`、2.4 GHz Wi-Fi、MQTT 和管理 Token 的运行时输入；
- GC2145 与 NMO432 配置校验，未填写完整 GPIO 时禁止启用；
- COM 口扫描、ESP-IDF v5.5.3 编译、确认后擦除、烧录和串口日志；
- 敏感字段日志脱敏。

启动 EXE 后输入 VPS 演示账号和密码，程序自动连接 `sg-0001`。账号和密码只保留在当前进程会话中。设备部署密钥应通过界面运行时输入或本机环境变量提供，不得写入 Git。

## Preliminary External Monitor

The preliminary external monitor is read-only. A viewer connects by device ID only after a valid MQTT uplink in the last 30 seconds. Synchronization is limited to monitoring scores/status and latest LLM advice; it does not synchronize profile, Wi-Fi, MQTT, fusion, thresholds, veto rules, or remote commands.

HTTPS is the normal mode. Plain HTTP is allowed only for the preliminary demo with `SG_ALLOW_INSECURE_HTTP=1`. Raw audio, raw video, MFCC, landmarks, and ROI remain local and do not appear in demo API or deployment examples.

## 医学免责声明

本设备是家庭健康风险提示工具，不是医疗诊断设备，不能替代医生的临床评估与治疗建议。若出现突发面部歪斜、言语不清、单侧肢体无力、视物异常、平衡障碍或意识改变等症状，无论设备结果如何，都应立即拨打 120，不等待复测或云端建议。
