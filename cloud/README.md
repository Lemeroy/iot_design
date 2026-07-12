# 卒中卫士 · 云端 (M5)

优云 VPS 自建 EMQX + InfluxDB + FastAPI + 火山豆包 doubao-1.5-lite。

## 目录

```
cloud/
├── docker-compose.yml
├── .env.example              # 复制为 .env 并填写
├── native/                   # 无 Docker/systemd 的原生部署
│   ├── install.sh            # 下载并校验固定版本运行时
│   ├── start.sh / stop.sh    # 服务生命周期
│   ├── status.sh             # 进程与端口状态
│   └── healthcheck.sh        # 自动化健康检查
├── scripts/
│   ├── gen_certs.sh          # 生成 EMQX 自签 TLS (无域名场景)
│   └── init_mqtt_users.sh    # 创建 MQTT 业务账号
├── emqx/
│   └── certs/                # 证书目录 (脚本填充)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # FastAPI 入口
│       ├── mqtt_bridge.py    # 订阅 uplink -> Influx + LLM -> 发布 downlink
│       ├── llm_advice.py     # 豆包 doubao-1.5-lite (Volcengine Ark OpenAI 兼容)
│       ├── db_influx.py      # InfluxDB 2.7 writer
│       └── schemas.py        # pydantic 契约
└── miniapp/                  # 微信小程序 (本地预览)
    ├── app.json / app.js / app.wxss
    └── pages/index/
```

## 当前云容器：原生部署（推荐）

当前实例的 PID 1 是 `tini`，并缺少 Docker-in-Docker 所需的
`CAP_SYS_ADMIN`/`CAP_NET_ADMIN`。请使用项目内原生运行时：

```bash
cd /opt/strokeguard/cloud
bash native/install.sh
bash native/start.sh
bash native/status.sh
bash native/healthcheck.sh
```

运行内容全部位于 `cloud/native/`：

- `runtime/`：EMQX 5.7.2、InfluxDB 2.7.11、Python venv
- `state/`：数据库和 EMQX 持久数据
- `logs/`：服务日志
- `run/`：PID 文件
- `downloads/`：经过 SHA256 校验的官方安装包

停止与重启：

```bash
bash native/stop.sh
bash native/start.sh
```

云容器整体重启后需要再次运行 `bash /opt/strokeguard/cloud/native/start.sh`。
若控制台支持“启动命令”，可直接填写该命令。脚本不会修改平台挂载的
`/entrypoint.sh`。

本地 Windows 一键上传并部署：

```powershell
powershell -ExecutionPolicy Bypass -File F:\iot_design\scripts\deploy_cloud_native_interactive.ps1
```

该窗口会分别在上传和远端部署时请求一次 SSH 密码，密码不会写入文件。

若云平台尚未开放公网业务端口，可先在本机建立 SSH 隧道：

```powershell
powershell -ExecutionPolicy Bypass -File F:\iot_design\scripts\open_cloud_tunnel.ps1
```

保持隧道窗口开启，并让上位机使用：

```powershell
$env:SG_MQTT_HOST="127.0.0.1"
$env:SG_MQTT_PORT="11883"
```

本机 FastAPI 为 `http://127.0.0.1:18000`，EMQX Dashboard 为
`http://127.0.0.1:18084`。这些端口只绑定本机回环地址。

## 标准 VPS：Docker Compose 部署

## 部署到 VPS (Ubuntu 22.04, Docker 已装)

### 1. 上传 cloud/ 到服务器

在**本地** PowerShell:

```powershell
# 用 scp 上传 (端口 22)
scp -P 22 -r F:\iot_design\cloud ubuntu@<VPS_HOST>:/tmp/strokeguard-cloud
ssh ubuntu@<VPS_HOST>
sudo mkdir -p /opt/strokeguard
sudo mv /tmp/strokeguard-cloud /opt/strokeguard/cloud
sudo chown -R ubuntu:ubuntu /opt/strokeguard/cloud
```

### 2. 配置 .env

在**服务器**上:

```bash
cd /opt/strokeguard/cloud
cp .env.example .env
vim .env    # 填写下列 5 项:
```

必填:
- `EMQX_DASHBOARD_PASS` — EMQX 18083 管理面板密码
- `MQTT_APP_PASS` — backend 用的 MQTT 密码 (随机字符串)
- `MQTT_HOST_PASS` — host_pc 上位机用的 MQTT 密码 (随机)
- `INFLUX_TOKEN` — 长随机串, 用 `openssl rand -hex 32` 生成
- `VOLC_ARK_API_KEY` — 火山方舟 API Key

### 3. 生成 TLS 证书 (无域名, 用 IP)

```bash
cd /opt/strokeguard/cloud
bash scripts/gen_certs.sh <VPS_HOST>
```

生成 `emqx/certs/ca.crt server.crt server.key`. 客户端将来需要 `ca.crt`.

### 4. 启动

```bash
docker compose up -d
docker compose ps           # 三个容器都是 running
docker compose logs -f backend
```

### 5. 创建 MQTT 账号

```bash
bash scripts/init_mqtt_users.sh
```

### 6. 联调验证

```bash
# 后端健康
curl http://127.0.0.1:8000/health
# {"status":"ok","mqtt":true,"influx":true,"llm":true}

# 手动触发一次 LLM 建议 (不经过 MQTT)
curl -X POST http://127.0.0.1:8000/advice \
  -H "Content-Type: application/json" \
  -d '{
    "scores": {"face":25,"speech":40,"tongue":100,"eye":90,"csi":80,"final":45},
    "level": "danger",
    "profile": {"age":68,"gender":"M","conditions":["hypertension"],"meds":["aspirin"],"stroke_history":false},
    "reasons": ["mouth_angle 22.5deg"]
  }'
```

## host_pc 上位机连云

设置环境变量后启动主界面:

```powershell
$env:SG_MQTT_HOST="<VPS_HOST>"
$env:SG_MQTT_PORT="1883"          # 联调期先用明文; 生产改 8883 + SG_MQTT_TLS=1
$env:SG_MQTT_USER="<MQTT_DEVICE_USER>"
$env:SG_MQTT_PASS="<你在 .env 里填的 MQTT_HOST_PASS>"
$env:SG_DEVICE_ID="sg-0001"

python -m stroke_host.ui.main_window --source real --perception
# 勾选 UI 顶部 Cloud 复选框, 然后 Start
```

启动后:
- host_pc 每 10s (或 level 变化时) uplink 数值评分
- 后端订阅 uplink -> 写 Influx -> 调豆包 -> 发布 downlink
- host_pc 收到 downlink -> UI 建议卡片显示

## 数据契约

见 `backend/app/schemas.py`. 三条主管线:

| 方向 | Topic | 载荷 |
|------|-------|------|
| host->cloud | `strokeguard/<dev>/uplink` | `UplinkPayload` |
| cloud->device | `strokeguard/<dev>/downlink` | `DownlinkPayload` |
| miniapp<-cloud | HTTP `/devices/<dev>/latest` | `LatestResp` |

**隐私铁律**: 云端接收的载荷**只有数值分与 profile**, 不含 jpeg/mfcc/坐标. `mqtt_pub.py` 已做严格过滤.

## 微信小程序本地预览

无 AppID (touristappid) 只能在**微信开发者工具**里预览:

1. 装 [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
2. 打开 `cloud/miniapp/` 目录, 选 "无 AppID 测试"
3. `app.js` 里的 `apiBase` 改成你的 VPS IP
4. 顶部工具 -> 详情 -> 本地设置 -> 勾选 "不校验合法域名..."
5. 编译预览

真机预览需要注册 AppID + HTTPS + 域名 ICP 备案, 属于毕设外围, M5 不做.
