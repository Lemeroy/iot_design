# 卒中卫士初赛演示验收记录

日期：2026-07-14

## 已通过

- [x] PC 全量自动测试：`300 passed`。
- [x] 新桌面入口不导入模拟源、PC 感知、录制、TTS 或 Keyring 模块。
- [x] 真实数据结构下 F/S/T/E 为 `null` 时显示“未接入”。
- [x] `level=insufficient` 时融合评分显示“未形成”，不把无效 `0` 显示为危险评分。
- [x] 云端不可达、登录失效、设备离线和数据未接入具有不同界面状态。
- [x] 设备维护页可编辑部署 YAML，并显示 ESP-IDF、固件目录和 COM 口。
- [x] 本机识别 ESP-IDF `5.5.3`，本机识别 S3 串口 `COM3`。
- [x] 擦除必须勾选确认，并再次确认具体 COM 口。
- [x] 实际 Windows 截图验证演示页和维护页无文字重叠。
- [x] `StrokeGuard-Demo.exe` 可启动登录窗口并干净退出，无孤儿进程。
- [x] EXE 内含无密钥 `device-deployment.example.yaml`。
- [x] 开发 ZIP 包含新桌面、部署和 IDF 脚本，且不含 `.env`、本地 YAML、缓存、日志、生成 sdkconfig 或原始数据。

## 当前发布文件

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `StrokeGuard-Demo.exe` | 50,857,682 | `14ADFCCD1252CD5253648ADBDF86F9166EFDBE1F7F34CA7D285F0132F27893C9` |
| `StrokeGuard-Developer-Handoff.zip` | 323,287 | `67BAF002D0D99FEEBE784C43C5EBFCF67C714E26D4A5259369BB3928195B31B4` |

## 待恢复 VPS 后复验

- [ ] `http://106.75.229.61:8000/health` 返回 HTTP 200，且 `mqtt/influx/llm` 为 `true`。
- [ ] EXE 登录后自动连接真实设备 `sg-0001`。
- [ ] S3 不连接 PC 时，页面显示最近 30 秒真实 CSI 上行。
- [ ] 页面显示 S3 权威 `level/reasons/veto_by`，不由大模型覆盖。
- [ ] 页面显示最新已完成豆包建议、来源和时间戳。
- [ ] 断开 S3 后超过 30 秒显示“设备离线”，不生成替代分数。

2026-07-14 验收时公网 `/health` 返回 HTTP 502。无密码 SSH 探测返回
`Permission denied (publickey,password)`，因此未在自动化中使用或暴露 VPS 密码。
恢复服务器后执行：

```powershell
ssh -t ubuntu@106.75.229.61 "sudo bash -lc 'cd /opt/strokeguard/cloud && bash native/start.sh && bash native/status.sh'"
```

该命令会在当前 PowerShell 中安全提示输入 SSH 密码和必要的 sudo 密码。目录
来自本仓库 `cloud/native/deploy_remote.sh` 的正式部署约定。

## 未执行的破坏性操作

- [ ] 未擦除 COM3。
- [ ] 未重新烧录固件。

只有在明确需要更新固件且已确认部署 YAML、板型 N16R8、GPIO 和目标 COM 口后，
才执行擦除与烧录。未执行不能写成“通过”。
