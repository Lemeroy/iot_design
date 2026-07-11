#!/usr/bin/env bash
# 卒中卫士 M5 VPS 一键部署
# 用法: 在 VPS 上执行
#   chmod +x deploy.sh && bash deploy.sh
set -euo pipefail

CLOUD_DIR="/opt/strokeguard/cloud"
cd "$CLOUD_DIR"

echo "=== StrokeGuard M5 VPS Deploy ==="

# ---- .env ----
if [ ! -f .env ]; then
    cp .env.example .env
    echo ">> 已生成 .env, 请先填写 MQTT/Influx 密码后重新执行此脚本"
    exit 0
fi

# Windows 生成的 .env 可能包含 UTF-8 BOM 和 CRLF，bash source 前先清理。
sed -i '1s/^\xEF\xBB\xBF//' .env
sed -i 's/\r$//' .env

set -a
. ./.env
set +a

require_env() {
    local name="$1"
    local value="${!name:-}"
    if [ -z "$value" ] || [[ "$value" == CHANGE_THIS* ]]; then
        echo "!! $name 未配置，请编辑 $CLOUD_DIR/.env"
        exit 1
    fi
}

require_csv_safe() {
    local name="$1"
    local value="${!name:-}"
    if [[ "$value" == *","* || "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
        echo "!! $name 不能包含逗号或换行，便于生成 EMQX bootstrap CSV"
        exit 1
    fi
}

require_env EMQX_DASHBOARD_PASS
require_env MQTT_APP_USER
require_env MQTT_APP_PASS
require_env MQTT_HOST_USER
require_env MQTT_HOST_PASS
require_env INFLUX_ADMIN_PASS
require_env INFLUX_TOKEN

for key in MQTT_APP_USER MQTT_APP_PASS MQTT_HOST_USER MQTT_HOST_PASS; do
    require_csv_safe "$key"
done

if [ -z "${VOLC_ARK_API_KEY:-}" ] || [ "${VOLC_ARK_API_KEY:-}" = "REPLACE_ME_ARK_KEY" ]; then
    echo ">> VOLC_ARK_API_KEY 未配置：云端建议将使用本地 fallback 文案"
fi

# ---- EMQX built-in DB bootstrap users ----
mkdir -p emqx
umask 077
cat > emqx/auth-built-in-db-bootstrap.csv <<EOF
user_id,password,is_superuser
${MQTT_APP_USER},${MQTT_APP_PASS},false
${MQTT_HOST_USER},${MQTT_HOST_PASS},false
EOF

# ---- TLS certs (本地 dev 跳过, 生产可保留) ----
if [ ! -f docker-compose.override.yml ]; then
    cat > docker-compose.override.yml <<'OVERRIDE'
services:
  emqx:
    volumes: []
    environment:
      EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__KEYFILE: ""
      EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__CERTFILE: ""
      EMQX_LISTENERS__SSL__DEFAULT__ENABLED: "false"
OVERRIDE
    echo ">> 已创建 docker-compose.override.yml (跳过 TLS)"
fi

# ---- Docker daemon ----
if ! docker info >/dev/null 2>&1; then
    echo ">> Docker daemon 未运行，尝试启动 docker 服务"
    systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true
    sleep 3
fi

if ! docker info >/dev/null 2>&1; then
    echo "!! Docker daemon 不可用，请确认 VPS 已安装并启动 Docker"
    exit 1
fi

# ---- 启动 ----
echo ">> docker compose up -d"
docker compose up -d --build

echo ">> 等待 10 秒让 EMQX/InfluxDB 初始化..."
sleep 10

# ---- 创建 MQTT 用户 (EMQX 5.7) ----
echo ">> 确认 MQTT 账号"
bash scripts/init_mqtt_users.sh

# ---- 验证 ----
echo ""
echo "=== 容器状态 ==="
docker compose ps

echo ""
echo "=== 健康检查 ==="
sleep 3
curl -s http://localhost:8000/health || echo "(后端可能还在启动, 等 10 秒再试)"
echo ""

echo ""
echo "=== 部署完成 ==="
echo "EMQX Dashboard: http://$(curl -s ifconfig.me):18083 (admin / <见 VPS .env 的 EMQX_DASHBOARD_PASS>)"
echo "FastAPI:         http://$(curl -s ifconfig.me):8000/docs"
echo ""
echo "本地 GUI 设置环境变量后启动:"
echo "  \$env:SG_MQTT_HOST='$(curl -s ifconfig.me)'"
echo "  \$env:SG_MQTT_PORT='1883'"
echo "  \$env:SG_MQTT_USER='${MQTT_HOST_USER}'"
echo "  \$env:SG_MQTT_PASS='<见 VPS /opt/strokeguard/cloud/.env 的 MQTT_HOST_PASS>'"
