# 卒中卫士云端原生部署设计

日期：2026-07-11

> 架构更新：本文件只描述云端部署。运行时 uplink 发布者已由 PC 改为 ESP32-S3；系统边界以 [独立镜端架构设计](2026-07-11-standalone-edge-mirror-design.md) 为准。

## 目标

在当前受限 Ubuntu 22.04 云容器中部署 EMQX、InfluxDB 和 FastAPI，保持 M5 数据契约不变，不依赖 Docker、systemd 或容器特权能力。所有部署脚本、配置模板和运行数据入口位于项目的 `cloud/native/` 目录。

## 环境结论

当前云环境的 PID 1 为 `tini -- sleep infinity`，根文件系统为 overlay，并缺少 `CAP_SYS_ADMIN` 与 `CAP_NET_ADMIN`。Docker 守护进程无法创建 NAT/iptables 规则，因此 Docker Compose 方案保留但不用于该环境。

## 方案

采用项目内自包含运行时：

- EMQX 5.7.2 使用官方 Ubuntu 22.04 amd64 发行包，安装到 `cloud/native/runtime/emqx/`。
- InfluxDB 2.7.11 使用官方 Linux amd64 发行包，安装到 `cloud/native/runtime/influxdb/`。
- FastAPI 使用 Python 3 venv，安装到 `cloud/native/runtime/venv/`。
- 持久数据放在 `cloud/native/state/`，日志放在 `cloud/native/logs/`，PID 文件放在 `cloud/native/run/`。
- 生成目录全部加入 `.gitignore`，仓库只保存脚本、模板和文档。

## 管理接口

新增以下脚本：

- `cloud/native/install.sh`：检查平台与依赖，下载运行时，创建 Python venv。
- `cloud/native/start.sh`：加载 `cloud/.env`，按 InfluxDB、EMQX、FastAPI 顺序启动，并等待各服务就绪。
- `cloud/native/stop.sh`：按 FastAPI、EMQX、InfluxDB 顺序停止，只处理 PID 文件指向且属于本运行目录的进程。
- `cloud/native/status.sh`：显示进程、端口和 HTTP 健康状态，不输出密码或令牌。
- `cloud/native/healthcheck.sh`：对 InfluxDB、EMQX、FastAPI 执行机器可读检查，任一必需服务失败即返回非零退出码。
- `scripts/deploy_cloud_native_interactive.ps1`：上传 `cloud/`，保留远端旧目录备份，执行安装、启动和健康检查。

## 网络与配置

- EMQX MQTT：`0.0.0.0:1883`。
- EMQX Dashboard：`0.0.0.0:18083`。
- InfluxDB：`127.0.0.1:8086`，不暴露公网。
- FastAPI：`0.0.0.0:8000`。
- FastAPI 原生环境使用 `MQTT_HOST=127.0.0.1`、`INFLUX_URL=http://127.0.0.1:8086`。
- 密码、InfluxDB token 和大模型 API Key 继续只从 `cloud/.env` 读取，不写入日志、命令行或版本控制。
- 豆包/OpenAI 兼容 API Key 未配置时，后端继续使用现有本地 fallback 建议文本。

## 初始化

首次启动 InfluxDB 后，调用其本机 setup HTTP API 创建组织、bucket、管理员和 token；后续启动检测已初始化状态，不重复覆盖数据。

首次启动 EMQX 后，通过本机 Dashboard API 创建或更新 backend 与 host_pc MQTT 用户。EMQX 必须关闭匿名访问；初始化失败时 FastAPI 不启动，避免形成无认证的 MQTT 服务。

## 数据流与隐私

ESP32-S3 仅向 `strokeguard/<device_id>/uplink` 上传数值评分和用户档案。FastAPI 订阅后写入 InfluxDB，调用轻量大模型或 fallback 生成建议，再向 `strokeguard/<device_id>/downlink` 发布文本。PC 不代理该运行链路。原始 JPEG、音频、MFCC 和关键点数据不得进入云端。

## 进程恢复边界

当前云容器没有系统服务管理器。`start.sh` 使用 `nohup`、PID 文件和健康等待维持服务，并可重复执行。容器进程被重启后，需要再次运行 `cloud/native/start.sh`；项目提供单一启动命令，供后续填写到云平台的“启动命令”设置。脚本不修改宿主挂载的 `/entrypoint.sh`。

## 错误处理

- 下载包使用固定版本和 SHA256 校验值；校验失败立即停止安装。
- 启动前验证必填环境变量，拒绝 `CHANGE_THIS` 占位值。
- 各服务采用有上限的条件轮询，不使用固定长等待作为成功判据。
- PID 文件陈旧时先验证实际进程，再清理 PID 文件；不按进程名批量终止。
- 健康检查和日志不显示任何 secret。

## 测试与验收

- 本地契约测试检查脚本语法、目录隔离、secret 不回显、端口绑定和启动顺序。
- Shell 脚本执行 `bash -n`，PowerShell 上传脚本执行 AST 解析。
- 远端验收要求 EMQX、InfluxDB、FastAPI 三个进程运行；`GET /health` 返回 `status=ok`、`mqtt=true`、`influx=true`。
- 未配置大模型 Key 时允许 `llm=false`，但 `POST /advice` 必须返回 fallback 文本。
- MQTT 联调必须验证数值 uplink 能触发 downlink；不得上传原始音视频。

## 非目标

- 本阶段不修改微信小程序功能。
- 本阶段不启用 MQTT TLS 8883；先完成受限环境下的明文 1883 联调，生产化时再恢复证书和 TLS。
- 本阶段不承诺容器平台级自动重启，除非云平台提供可配置启动命令。
