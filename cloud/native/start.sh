#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ensure_dirs
load_env
require_env \
    EMQX_DASHBOARD_PASS MQTT_APP_USER MQTT_APP_PASS MQTT_HOST_USER MQTT_HOST_PASS \
    INFLUX_ADMIN_USER INFLUX_ADMIN_PASS INFLUX_ORG INFLUX_BUCKET INFLUX_TOKEN

influx_bin="$runtime_dir/influxdb/usr/bin/influxd"
emqx_bin="$runtime_dir/emqx/bin/emqx"
python_bin="$runtime_dir/venv/bin/python"

[ -x "$influx_bin" ] || { echo "run native/install.sh first" >&2; exit 1; }
[ -x "$emqx_bin" ] || { echo "run native/install.sh first" >&2; exit 1; }
[ -x "$python_bin" ] || { echo "run native/install.sh first" >&2; exit 1; }

start_influx() {
    local pid_file="$run_dir/influxdb.pid"
    mkdir -p "$state_dir/influxdb/engine"
    if pid_matches "$pid_file" "$influx_bin"; then
        echo "InfluxDB: already running"
    else
        rm -f "$pid_file"
        nohup "$influx_bin" \
            --bolt-path "$state_dir/influxdb/influxd.bolt" \
            --engine-path "$state_dir/influxdb/engine" \
            --http-bind-address 127.0.0.1:8086 \
            --reporting-disabled \
            >"$logs_dir/influxdb.log" 2>&1 &
        echo "$!" > "$pid_file"
    fi
    wait_http "http://127.0.0.1:8086/health" 45 1
    "$python_bin" "$native_root/bootstrap.py" influx
}

start_emqx() {
    local pid_file="$run_dir/emqx.pid"
    local cookie_file="$state_dir/emqx/node.cookie"
    mkdir -p "$state_dir/emqx" "$logs_dir/emqx"
    if [ ! -s "$cookie_file" ]; then
        "$python_bin" -c 'import secrets; print(secrets.token_hex(32))' > "$cookie_file"
        chmod 600 "$cookie_file"
    fi
    cp "$native_root/config/emqx-base.hocon.template" "$runtime_dir/emqx/etc/emqx.conf"
    if pid_matches "$pid_file" "$runtime_dir/emqx"; then
        echo "EMQX: already running"
    else
        rm -f "$pid_file"
        export EMQX_NODE__DATA_DIR="$state_dir/emqx"
        export EMQX_NODE__COOKIE="$(cat "$cookie_file")"
        export EMQX_LOG__FILE__DEFAULT__PATH="$logs_dir/emqx/emqx.log"
        export EMQX_DASHBOARD__DEFAULT_USERNAME="admin"
        export EMQX_DASHBOARD__DEFAULT_PASSWORD="$EMQX_DASHBOARD_PASS"
        export EMQX_AUTHENTICATION__1__MECHANISM="password_based"
        export EMQX_AUTHENTICATION__1__BACKEND="built_in_database"
        export EMQX_AUTHENTICATION__1__USER_ID_TYPE="username"
        nohup "$emqx_bin" foreground >"$logs_dir/emqx-console.log" 2>&1 &
        echo "$!" > "$pid_file"
    fi
    wait_http "http://127.0.0.1:18083/status" 60 1
    "$python_bin" "$native_root/bootstrap.py" emqx
}

start_backend() {
    local pid_file="$run_dir/backend.pid"
    if pid_matches "$pid_file" "$runtime_dir/venv"; then
        echo "FastAPI: already running"
        return 0
    fi
    rm -f "$pid_file"
    export MQTT_HOST="127.0.0.1"
    export MQTT_PORT="1883"
    export MQTT_USER="$MQTT_APP_USER"
    export MQTT_PASS="$MQTT_APP_PASS"
    export INFLUX_URL="http://127.0.0.1:8086"
    export SG_DEMO_USER="${SG_DEMO_USER:-}"
    export SG_DEMO_PASSWORD="${SG_DEMO_PASSWORD:-}"
    export SG_DEMO_SESSION_SECRET="${SG_DEMO_SESSION_SECRET:-}"
    export SG_ALLOW_INSECURE_HTTP="${SG_ALLOW_INSECURE_HTTP:-}"
    export PUSHPLUS_ENABLED="${PUSHPLUS_ENABLED:-0}"
    export PUSHPLUS_TOKEN="${PUSHPLUS_TOKEN:-}"
    export PUSHPLUS_DEVICE_NAME="${PUSHPLUS_DEVICE_NAME:-}"
    cd "$cloud_root/backend"
    nohup "$python_bin" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
        >"$logs_dir/backend.log" 2>&1 &
    echo "$!" > "$pid_file"
    wait_http "http://127.0.0.1:8000/health" 45 1
}

start_influx
start_emqx
start_backend
"$native_root/healthcheck.sh"
