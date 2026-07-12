# 卒中卫士开发移交说明

## 交付入口

- 演示程序：`dist/StrokeGuard-Demo.exe`
- 开发移交包：`dist/StrokeGuard-Developer-Handoff.zip`
- 一键重建：`powershell -ExecutionPolicy Bypass -File scripts/build_release.ps1`

移交 ZIP 由 `git archive HEAD` 生成，只包含已提交源码。它不包含 Wi-Fi、
MQTT、VPS、大模型或管理密钥，不包含 `sdkconfig`、`.env`、录制数据、构建
目录、缓存、日志和 DOCX。

## 当前可运行能力

- ESP32-S3 N16R8 独立运行 CSI、确定性五模态融合框架、本地告警、USB 调试
  遥测、MQTT 数值契约和局域网档案管理 API。
- PC PyQt5 工具可监控 S3 调试遥测，通过表单/YAML 管理有限用户档案；Token
  存入系统 Keyring，revision 冲突需人工选择本地或设备版本。
- 云端源码包含 EMQX、InfluxDB、FastAPI、数值存储、大模型建议和小程序。
- 当前 PC 全量回归证据为 `197 passed`；固件生产镜像为 `0xee600`，2 MB
  应用分区余量 53%。数字来自 2026-07-12 本机测试与构建输出。

## 已知限制

- GC2145、INMP441、ST7789、MAX98357A 等外设尚未到货，Kconfig 引脚默认
  `-1`；必须按实物原理图确认接线后再启用，禁止猜测引脚。
- 当前没有视觉/语音训练权重。GC2145 的 F/T/E 与 INMP441 的 S 仍需采集
  合规数据、训练、量化并在真机评测；不得编造灵敏度或特异度。
- 现有 VPS 的 SSH 会话被立即关闭，公网 FastAPI 8000 超时，MQTT 1883
  仅能建立 TCP 而无 CONNACK。云端链路未通过最终验收，恢复服务后需重新
  跑 `/health`、数值 uplink、InfluxDB、建议 downlink 和 latest 查询。
- 当前局域网管理使用 HTTP，仅适合可信开发网络。生产需 TLS 或安全隧道。
- Arm 因镜面视野限制不单独测量；舌偏只作辅助参考，不设置单项否决。

## 开发环境

- Windows PowerShell
- ESP-IDF v5.5.3
- ESP32-S3-WROOM-1 N16R8，当前开发串口 COM3
- Python 3.10+；本机验证使用 Python 3.14 与 PyQt5

PC 初始化：

```powershell
cd host_pc
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[ui,dev]"
.venv\Scripts\python.exe -m pytest tests `
  --basetemp=F:\iot_design\.pytest-native-root\handoff `
  -p no:cacheprovider
```

固件构建：

```powershell
cd firmware_esp32
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
idf.py -p COM3 flash monitor
```

真实凭据只写入被 Git 忽略的 `firmware_esp32/sdkconfig`、云端 `.env` 和 PC
系统 Keyring。移交前后都应运行敏感信息扫描，并检查 Git 状态只包含预期文件。

## 医学与隐私边界

本项目是风险提示和就医提醒工具，不是诊断设备。原始音视频只在镜端本地
处理，绝不上云；云端和大模型只接收数值评分与有限用户档案。若出现突发
FAST/BE-FAST 症状，无论设备结果如何，应立即拨打 120。
