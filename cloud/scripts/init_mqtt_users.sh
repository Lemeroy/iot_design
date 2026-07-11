#!/usr/bin/env bash
# 在 EMQX 内置数据库创建业务账号 (docker compose up 之后运行一次)
#
# 依赖: cloud/.env 已填好 MQTT_APP_USER/PASS 与 MQTT_HOST_USER/PASS
#
# 用法:
#   bash scripts/init_mqtt_users.sh

set -euo pipefail

# 加载 .env
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
set -a
. "$ROOT_DIR/.env"
set +a

CONTAINER="sg-emqx"

echo "==> 创建 MQTT 账号 (通过 emqx_ctl authentication)"

AUTH_ID="password_based%3Abuilt_in_database"

json_body() {
    local user="$1"
    local pass="$2"
    printf '{"user_id":"%s","password":"%s"}' "$user" "$pass"
}

create_or_update_user() {
    local user="$1"
    local pass="$2"
    local tmp
    tmp="$(mktemp)"

    local code
    code="$(
        curl -sS -o "$tmp" -w "%{http_code}" \
            -u "admin:${EMQX_DASHBOARD_PASS}" \
            -H "Content-Type: application/json" \
            -X POST "http://127.0.0.1:18083/api/v5/authentication/${AUTH_ID}/users" \
            -d "$(json_body "$user" "$pass")" || true
    )"

    if [ "$code" = "200" ] || [ "$code" = "201" ] || [ "$code" = "204" ]; then
        echo "  $user 已创建"
        rm -f "$tmp"
        return 0
    fi

    if [ "$code" = "400" ] || [ "$code" = "409" ]; then
        code="$(
            curl -sS -o "$tmp" -w "%{http_code}" \
                -u "admin:${EMQX_DASHBOARD_PASS}" \
                -H "Content-Type: application/json" \
                -X PUT "http://127.0.0.1:18083/api/v5/authentication/${AUTH_ID}/users/${user}" \
                -d "{\"password\":\"$pass\"}" || true
        )"
        if [ "$code" = "200" ] || [ "$code" = "204" ]; then
            echo "  $user 已更新"
            rm -f "$tmp"
            return 0
        fi
    fi

    echo "!! $user 创建/更新失败 HTTP $code"
    cat "$tmp"
    rm -f "$tmp"
    return 1
}

create_or_update_user "$MQTT_APP_USER" "$MQTT_APP_PASS"
create_or_update_user "$MQTT_HOST_USER" "$MQTT_HOST_PASS"

echo "==> 完成"
