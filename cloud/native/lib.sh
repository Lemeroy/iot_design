#!/usr/bin/env bash

set -euo pipefail

native_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cloud_root="$(cd "$native_root/.." && pwd)"
runtime_dir="$native_root/runtime"
state_dir="$native_root/state"
logs_dir="$native_root/logs"
run_dir="$native_root/run"
downloads_dir="$native_root/downloads"

ensure_dirs() {
    mkdir -p "$runtime_dir" "$state_dir" "$logs_dir" "$run_dir" "$downloads_dir"
}

load_env() {
    if [ ! -f "$cloud_root/.env" ]; then
        echo "missing configuration: $cloud_root/.env" >&2
        return 1
    fi
    sed -i '1s/^\xEF\xBB\xBF//' "$cloud_root/.env"
    sed -i 's/\r$//' "$cloud_root/.env"
    set -a
    . "$cloud_root/.env"
    set +a
}

require_env() {
    local name value
    for name in "$@"; do
        value="${!name:-}"
        case "$value" in
            ""|CHANGE_THIS*|REPLACE_ME*)
                echo "required setting is missing: $name" >&2
                return 1
                ;;
        esac
    done
}

pid_matches() {
    local pid_file="$1"
    local expected="$2"
    local pid
    [ -f "$pid_file" ] || return 1
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [ -d "/proc/$pid" ] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -Fq -- "$expected"
}

wait_http() {
    local url="$1"
    local max_attempts="${2:-30}"
    local delay="${3:-1}"
    local attempt
    for ((attempt = 1; attempt <= max_attempts; attempt++)); do
        if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$delay"
    done
    echo "health check timed out: $url" >&2
    return 1
}

stop_pid() {
    local name="$1"
    local pid_file="$2"
    local expected="$3"
    local pid attempt
    if ! pid_matches "$pid_file" "$expected"; then
        rm -f "$pid_file"
        echo "$name: stopped"
        return 0
    fi
    pid="$(cat "$pid_file")"
    kill "$pid"
    for ((attempt = 1; attempt <= 20; attempt++)); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$pid_file"
            echo "$name: stopped"
            return 0
        fi
        sleep 1
    done
    echo "$name: did not stop within 20 seconds (pid $pid)" >&2
    return 1
}
