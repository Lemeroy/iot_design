# StrokeGuard PC 端 M1a

## 初赛演示入口（推荐）

```powershell
cd F:\iot_design\host_pc
.venv\Scripts\python.exe -m stroke_host.demo.window
```

该入口是 `StrokeGuard-Demo.exe` 的源码运行方式：默认登录 VPS 并连接真实设备 `sg-0001`，不读取模拟源、不运行 PC 感知管线，也不生成替代评分。设备维护页可编辑 `config/device-deployment.example.yaml`，填写本次运行使用的 Wi-Fi/MQTT/管理凭据，调用本机 ESP-IDF v5.5.3 完成编译、确认擦除、烧录和串口监视。

麦克风型号为 **NMO432**：3.3V 供电，I2S 引脚为 `SCK/BCLK`、`WS/LRCLK`、`SD/DIN`，并通过 `L/R` 选择声道。GC2145 与 NMO432 的 GPIO 未完整确认时保持 `enabled: false`，程序不会猜测引脚。

下文的模拟源、PC 感知和旧观察窗口仅供研发测试，不属于初赛 EXE 的演示入口。

上位机数据管线：ESP32 帧接入 + AES-GCM 加密落盘 + 24h 自动清理 + 用户档案。

## 目录

```
host_pc/
├── pyproject.toml
├── requirements.txt
├── config/
│   └── profile.yaml            # 用户档案 (age/conditions/meds/...)
├── stroke_host/
│   ├── main.py                 # 入口 CLI
│   ├── io/
│   │   ├── cdc_reader.py       # ESP32 USB-CDC 帧解析
│   │   ├── sim_source.py       # 无硬件桩 (M1a 默认)
│   │   ├── frame_recorder.py   # AES-GCM 落盘 + 定时清理
│   │   └── crc16.py            # 与固件对齐
│   ├── config/profile_loader.py
│   └── utils/crypto.py         # keyring master key + AESGCM
└── tests/                      # pytest (含 CRC 对拍 / 帧解析 / 加密 / 24h 清理)
```

## 安装 (Windows PowerShell)

```powershell
cd F:\物联网设计\host_pc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
```

## 跑桩数据源 (无 ESP32, M1a 默认)

```powershell
python -m stroke_host.main --source sim
# 每秒一帧 heartbeat, csi_score 60~95 随机游走
# Ctrl+C 停止, 落盘至 data\session_<时间>\frames.jsonl.enc
```

## 跑真机 (烧录线到手后)

```powershell
# 先确认哪个 COM 是数据口 (CDC0, Interface 0)
Get-CimInstance Win32_SerialPort | Select-Object Name,DeviceID,Description

python -m stroke_host.main --source cdc --port COM3
```

统计输出示例：

```
cdc stats: ok=612 crc_err=0 resync=1
```

## 实时观察窗口 (M1a Observer, tkinter)

零新增依赖，用于目视监控 csi_score 趋势。

```powershell
python -m stroke_host.gui.observer --source sim
# 或真机
python -m stroke_host.gui.observer --source cdc --port COM3
```

窗口包含：
- 交通灯：red (<30) / yellow (<60) / green (>=60)
- 大号 csi 数字 + 最近 60 帧 sparkline
- 统计：frames / fps / cdc ok/crc_err/resync / 当前 session 目录名
- 日志尾 30 行
- 顶部工具条：切 sim/cdc、改 port、勾选 Record、Start/Stop

## M2 感知算法 (F 面部对称 + S 语音清晰度)

新增依赖：`mediapipe` (可选，未装则 F 分不可用)

```powershell
pip install mediapipe
```

真源模式跑 PC 摄像头+麦克风，同时出 F/S 分：

```powershell
python -m stroke_host.main --source real --perception --no-record
```

输出示例：

```
[#12] data csi=None ts=2  F=94 (mouth_angle 1.7deg)  S=63
[#13] data csi=None ts=2  F=97
```

模块概览：

| 模块 | 功能 | 备注 |
|------|------|------|
| `perception/face_detect.py` | mediapipe FaceMesh 468/478 点封装 (refine_landmarks=True 含虹膜) | 单人 |
| `perception/face_symmetry.py` | 口角连线 θ → F 分 (0-100) | 用双眼外眦补偿头部面内旋转 |
| `perception/landmark68.py` | 468 → iBUG 68 点索引映射 | 供 dlib 兼容脚本复用 |
| `perception/mfcc.py` | 纯 numpy MFCC | 与嵌入式 C 版可 bitmatch |
| `perception/mic_source.py` | sounddevice 系统默认输入 | 16 kHz mono |
| `perception/speech_cnn.py` | S 分, CNN 未训 → 启发式 fallback | `p_clear` 综合 voiced_ratio/HNR/MFCC 稳态 |
| **`perception/tongue_deviation.py`** | Tongue 分 (辅助, 权重 0.08) | 下唇内侧近似, **低置信度不否决** |
| **`perception/eye_gaze.py`** | E 分 (权重 0.12) | mediapipe 虹膜, gaze 共轭比 + 眼裂对称性 |
| **`perception/csi_score.py`** | B 分 (权重 0.08) | 端侧已算, PC 侧透传 |

### Dr.Chen 阈值 (v0, 待临床验证)

| 模态 | 计算 | Danger 线 | Warning 线 |
|------|------|--------|-----------|
| F 面部 | `100 - 4·θ` | θ ≥ 20° | θ > 10° |
| S 言语 | `100·p_clear` | score<35 且 p<0.4 | score<55 |
| T 舌偏 | 分段 (辅助) | r≥0.15 → 30 | r≥0.10 → 50-70 |
| E 眼动 | `100 - 200·|Δgaze|` | dg≥0.30 或 lid_asym | dg≥0.15 |
| B 平衡 (CSI) | 端侧直接输出 | <30 | <60 |

**局限（明示）**：
- F: mediapipe 二维投影对大侧脸敏感
- S: 无临床构音数据集，走启发式，需 SNR>15dB
- T: 无舌头分割模型，本版为下唇偏移近似，**灵敏度低，仅参考**
- E: 需正视镜头 ±20°；戴墨镜/极暗光 iris 失败 → unavailable
- B: 无外发射器，反映"存在感/剧烈动作"而非精确平衡

## 观察窗口升级 (M2+M3, 5 模态卡片)

```powershell
python -m stroke_host.gui.observer --source real --perception
```

窗口现包含：
- 总指示交通灯 + 大号"最低模态分"数字（宁误报保守策略）
- **5 张模态卡片**：F / S / T / E / B，各自变色 + 数字
- 60 帧 sparkline
- Perception 复选框（勾选后 data 帧走完整感知流水线）

## M4 主界面 (PyQt5 · 正式版)

新增依赖：

```powershell
pip install -e ".[ui]"     # 安装 PyQt5 + pyttsx3
```

启动：

```powershell
python -m stroke_host.ui.main_window --source real --perception
```

功能：

- **五模态融合**：`final = 0.35·F + 0.35·S + 0.08·T + 0.14·E + 0.08·B`
- **单项否决**（Ark + Dr.Chen 会签，宁误报）：
  - F ≤ 30 或 mouth_angle ≥ 20° → **danger**（红灯闪烁 + 语音"检测到面部不对称,请立即就医并拨打 120"）
  - S ≤ 35 且 p_clear < 0.4 → **danger**（"检测到言语不清..."）
  - E < 30 或 B < 30 → 从 normal 提升为 **warning**
- **不可用模态自适应**：某模态 score=-1 时权重按比例重分；可用总权重 <0.5 → level="insufficient"
- **UI 组成**：
  - 左：180×180 交通灯（danger 时 400ms 闪烁）+ 大号 final + 中文 level 文本 + reasons 面板
  - 右：5 张模态卡片（边框跟随各自阈值变色）
  - 语音引导按钮：**请微笑** / **请说"你好中国"** / **请正视镜头**
  - 顶部工具条：source / port / Record / Perception / Voice alerts
  - 底部：帧率统计 + 完整免责声明
- **TTS**：`pyttsx3` (SAPI5，Windows 自带)，异步线程 + 3s 冷却期防轰炸，未装或初始化失败自动降级为静默
- **加密录制**：Record 勾选时启用 AES-GCM + 24h 清理 (M1a 一致)

## 完整模块清单

```
host_pc/stroke_host/
├── io/                  # M1a: CDC 帧解析 / sim / real / 加密落盘
├── perception/          # M2+M3: F / S / T / E / B
├── fusion/              # M4: 加权 + 单项否决 + 分级
├── ui/                  # M4: PyQt5 主界面 + pyttsx3 TTS
├── gui/                 # M1a Observer (tk, 调试用)
├── config/              # profile.yaml 加载
├── utils/               # AES-GCM + keyring
└── main.py              # CLI 入口
```

## 测试

```powershell
pytest -q
```

覆盖：
- CRC16 与固件对拍向量 (`test_crc16.py`)
- 帧同步 / CRC 错帧丢弃 / 头前垃圾自动重同步 (`test_cdc_parser.py`)
- AES-GCM 往返 + 25h 前旧 session 被清理 + 当前 session 不被误删 (`test_frame_recorder.py`)
- `profile.yaml` 校验 (`test_profile.py`)
- Sim 源端到端跑通 (`test_integration_sim.py`)

## 隐私 & 安全

| 项 | 实现 |
|----|------|
| Master key | Windows 凭据管理器 (keyring)，`Service=StrokeGuard, Account=master-key` |
| 加密 | AES-256-GCM，每帧独立 12B nonce，AAD=device_id |
| 保留期 | 24 小时；后台线程每 30 分钟扫描一次 |
| 上云 | M1a **不上云**；M5 起只传数值评分 + profile |

## Quinn 验收 (M1a PC 端)

| # | 步骤 | 通过标准 |
|---|------|--------|
| P1 | `pip install -e ".[dev]"` | 无 error |
| P2 | `pytest -q` | 全绿 |
| P3 | `python -m stroke_host.main --source sim --max-frames 10` | 打印 10 条 heartbeat 后退出 |
| P4 | 查看 `data\session_*\frames.jsonl.enc` | 存在且非空 |

真机联调 (Q4-Q6) 待烧录线到手后一起跑。

## 已知局限

- SimSource 只产 heartbeat，不产图像/音频；M2 开始加 PC 摄像头/麦克风真源
- 时间戳来自 `time.time()`，未做 ESP32 端时间同步（M5 SNTP 处理）
- 无 SNTP 时 ESP32 `ts` 是启动后秒数，PC 侧只信 `ts_recv`
