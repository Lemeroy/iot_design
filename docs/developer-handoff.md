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
- 初赛 PyQt5 演示程序默认连接 VPS 上的真实设备 `sg-0001`，显示真实评分、
  S3 风险等级和豆包建议；不生成模拟数据，也不把 PC 作为镜端运行依赖。
- 演示程序的设备维护页支持部署 YAML、COM 扫描、ESP-IDF v5.5.3 编译、
  二次确认擦除、烧录和串口监视，所有日志按已解析配置脱敏。
- 云端源码包含 EMQX、InfluxDB、FastAPI、数值存储、大模型建议和小程序。
- 测试数量和发布文件 SHA-256 以每次 `build_release.ps1` 的最新输出为准，
  不在移交文档中固化可能过期的数字。

## 已知限制

- GC2145、NMO432、ST7789、MAX98357A 的 Kconfig 引脚默认 `-1`；必须按
  实物原理图确认接线后再启用，禁止猜测引脚。NMO432 为 3.3V I2S 麦克风，
  使用 SCK、WS、SD 和 L/R 声道选择。
- 当前没有视觉/语音训练权重。GC2145 的 F/T/E 与 NMO432 的 S 仍需采集
  合规数据、训练、量化并在真机评测；不得编造灵敏度或特异度。
- VPS 的 MQTT→InfluxDB→豆包建议→S3 下行链路已完成真机验收；公网演示仍
  应在每次答辩前重新检查 `/health`、设备 30 秒在线窗口和建议时间戳。
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

## 机械模型交接

桌面初赛演示机的参数化 OpenSCAD、已验证 STL、装配/爆炸渲染、TinkerCAD
manifest、尺寸表和打印流程位于
[`mechanical/desktop_enclosure`](../mechanical/desktop_enclosure/README.md)。
OpenSCAD/STL 是制造依据，TinkerCAD 只用于在线展示。移交前应重新运行该目录的
导出脚本和 pytest，并先打印 fit coupon；不得把未实测的板孔距、接口偏移或前板
厚度写成固定机械参数。

## 医学与隐私边界

本项目是风险提示和就医提醒工具，不是诊断设备。原始音视频只在镜端本地
处理，绝不上云；云端和大模型只接收数值评分与有限用户档案。若出现突发
FAST/BE-FAST 症状，无论设备结果如何，应立即拨打 120。
