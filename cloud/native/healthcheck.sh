#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

check() {
    local name="$1" pid_file="$2" expected="$3" url="$4"
    pid_matches "$pid_file" "$expected" || {
        echo "$name process: failed" >&2
        return 1
    }
    curl -fsS --max-time 5 "$url" >/dev/null || {
        echo "$name health: failed" >&2
        return 1
    }
    echo "$name: ok"
}

result=0
check "InfluxDB" "$run_dir/influxdb.pid" "$runtime_dir/influxdb/usr/bin/influxd" \
    "http://127.0.0.1:8086/health" || result=1
check "EMQX" "$run_dir/emqx.pid" "$runtime_dir/emqx" \
    "http://127.0.0.1:18083/status" || result=1
check "FastAPI" "$run_dir/backend.pid" "$runtime_dir/venv" \
    "http://127.0.0.1:8000/health" || result=1
exit "$result"
