#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ensure_dirs
result=0
stop_pid "FastAPI" "$run_dir/backend.pid" "$runtime_dir/venv" || result=1
stop_pid "EMQX" "$run_dir/emqx.pid" "$runtime_dir/emqx" || result=1
stop_pid "InfluxDB" "$run_dir/influxdb.pid" "$runtime_dir/influxdb/usr/bin/influxd" || result=1
exit "$result"
