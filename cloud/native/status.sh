#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

show_process() {
    local name="$1" pid_file="$2" expected="$3"
    if pid_matches "$pid_file" "$expected"; then
        echo "$name: running (pid $(cat "$pid_file"))"
    else
        echo "$name: stopped"
    fi
}

show_process "InfluxDB" "$run_dir/influxdb.pid" "$runtime_dir/influxdb/usr/bin/influxd"
show_process "EMQX" "$run_dir/emqx.pid" "$runtime_dir/emqx"
show_process "FastAPI" "$run_dir/backend.pid" "$runtime_dir/venv"

for endpoint in \
    "InfluxDB|http://127.0.0.1:8086/health" \
    "EMQX|http://127.0.0.1:18083/status" \
    "FastAPI|http://127.0.0.1:8000/health"; do
    name="${endpoint%%|*}"
    url="${endpoint#*|}"
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
        echo "$name HTTP: ok"
    else
        echo "$name HTTP: unavailable"
    fi
done
