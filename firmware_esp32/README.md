# StrokeGuard 固件 E1 (v0.5)

ESP32-S3-WROOM-1 (N16R8) · IDF v5.5.3 · **独立本地融合/告警** + Wi-Fi CSI + MQTT 数值上报 + USB-Serial-JTAG 调试遥测。

> v0.3 变更 (2026-07-10):
> - **CSI 算法升级为三特征融合** (借鉴 [RuView, MIT](https://github.com/ruvnet/RuView) 信号处理章节):
>   幅度 CV (0.40) + 相位方差 (0.40) + 运动带能量 (0.20)
> - 相位方差不受 AGC 影响, 静止/动作区分度更好
> - **新增 1 Hz ICMP ping 网关**保证 CSI 包流量 (STA 空闲时 CSI 极稀疏)
> - `task_csi` 加 5s **静默诊断日志**: 让 "回调未触发" 与 "样本不足" 两种情况可肉眼区分
>
> v0.2: 放弃 TinyUSB 双 CDC, 改用 IDF 内置 `usb_serial_jtag` 单口。

## 目录

```
firmware_esp32/
├── CMakeLists.txt
├── sdkconfig.defaults      # PSRAM OPI / usb_serial_jtag / CSI 使能
├── partitions.csv          # OTA 预留
└── main/
    ├── app_main.c          # 启动 & 心跳任务
    ├── app_config.h        # 全局宏 (含三特征权重)
    ├── usb_cdc_proto.*     # usb_serial_jtag + 帧封装
    ├── crc16.*             # CRC16-CCITT
    ├── csi_monitor.*       # CSI 采集 + 三特征打分 (RuView 借鉴)
    ├── csi_ping.c          # 1Hz ICMP keep-alive (RuView 借鉴)
    ├── frame_builder.*     # JSON 组包
    ├── Kconfig.projbuild   # menuconfig 里的 WiFi 配置
    └── log_tag.h
```

## 环境

- ESP-IDF **v5.5.3**，PowerShell (Windows)
- 已 `install.ps1 esp32s3` 并 `. $env:IDF_PATH\export.ps1`

## 配置 WiFi

```powershell
idf.py -p COM3 menuconfig
# -> "StrokeGuard M1a Config" -> 修改 WiFi SSID/Password -> S 保存 -> Q 退出
```

路由器必须提供 2.4 GHz Wi-Fi；ESP32-S3 不支持 5 GHz。建议锁 2.4 GHz **Ch6, 20MHz**。

## 构建 / 烧录 / 监视

```powershell
idf.py set-target esp32s3
idf.py build
idf.py -p COM3 flash monitor
```

**关键**: v0.2 只有**一个** COM 口, `flash` 和 `monitor` 用同一个 COM3.
`monitor` 里既能看到日志, 也能看到二进制帧(会显示为乱码, 属正常).
USB 帧仅供 PC 端 `stroke_host` 观察和调试；运行时融合、告警和 MQTT 不依赖 PC。

## 帧协议 v1

```
偏移  长度  字段
0     2B    A5 5A          magic
2     1B    ver = 0x01
3     1B    type           0x01=heartbeat, 0x02=data(M1b), 0xF0=log
4     2B    len (LE)       payload 长度
6     N     payload        UTF-8 JSON
6+N   2B    CRC16-CCITT    覆盖 ver..payload
```

payload 示例:

```json
{"type":"heartbeat","ts":123,"seq":42,"csi_score":87,"fw":"m1a-0.3"}
```

## CSI 三特征融合 (v0.3)

| 特征 | 计算 | 权重 | 含义 |
|------|------|------|------|
| 幅度 CV | `stddev / mean` 全带幅度 | 0.40 | 静止时子载波幅度稳 |
| 相位方差 | unwrap 后 `var(phase)` 参考子载波 | 0.40 | 抗 AGC, 动作敏感 |
| 运动带能量 | 相邻样本 L2 差分归一 | 0.20 | 动作剧烈度 |

分值 `= 100 - k·feature`, 再按权重线性加权。k 值 (`SG_CSI_K_*` 于 `app_config.h`) 需 M6 阶段实测标定。

## Quinn 独立验收 (v0.3)

| # | 步骤 | 通过标准 |
|---|------|--------|
| Q1 | `idf.py build` | 无 error |
| Q2 | `flash monitor` | 5s 内 `boot fw=m1a-0.3` |
| Q3 | 15s 内 | `WIFI GOT_IP` 与 `csi started (v0.3 3-feat fusion...)` |
| Q4 | 20s 内 | `ping keep-alive @ gw=xxx.xxx.xxx.xxx` |
| Q5 | 30s 内 | 心跳帧里 `csi_score` 从 `null` 变成 0-100 数字 |
| Q6 | 揉一下头/在镜前挥手 | `csi_score` 明显下跌 (>20 分), 静止后回升 |

## 已知局限

- 打分公式中的 `SG_CSI_K_*` 是经验初值, M6 前需实测标定 (静止/正常动作/剧烈动作三档做校准)
- 无外发射器 → CSI 反映"镜前存在感/剧烈动作", 不是精确平衡评估
- M1a 无外设, heartbeat 帧不含图像/音频, 仅 CSI 分与序号
- 相位 unwrap 只用参考子载波 (n_sub/2), 边缘 SC 抖动更大, 后续可换 SVD 主分量
