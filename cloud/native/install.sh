#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

EMQX_VERSION="5.7.2"
EMQX_ARCHIVE="emqx-5.7.2-ubuntu22.04-amd64.tar.gz"
EMQX_URL="https://www.emqx.com/en/downloads/broker/5.7.2/$EMQX_ARCHIVE"
EMQX_SHA256="338b90fe101d5802ff921324e2bb1b745f220f9a6c8a8a6f992ad25afe8804a5"

INFLUX_VERSION="2.7.11"
INFLUX_ARCHIVE="influxdb2-2.7.11_linux_amd64.tar.gz"
INFLUX_URL="https://download.influxdata.com/influxdb/releases/$INFLUX_ARCHIVE"
INFLUX_SHA256="8d7872013cad3524fb728ca8483d0adc30125ad1af262ab826dcf5d1801159cf"

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "missing required command: $1" >&2
        exit 1
    }
}

download_verified() {
    local url="$1"
    local destination="$2"
    local expected_sha="$3"
    local actual_sha
    if [ ! -f "$destination" ]; then
        echo "downloading $(basename "$destination")"
        curl -fL --retry 3 --connect-timeout 15 -o "$destination.part" "$url"
        mv "$destination.part" "$destination"
    fi
    actual_sha="$(sha256sum "$destination" | awk '{print $1}')"
    if [ "$actual_sha" != "$expected_sha" ]; then
        echo "checksum mismatch: $(basename "$destination")" >&2
        rm -f "$destination"
        exit 1
    fi
}

install_emqx() {
    local archive="$downloads_dir/$EMQX_ARCHIVE"
    local target="$runtime_dir/emqx"
    [ -x "$target/bin/emqx" ] && return 0
    download_verified "$EMQX_URL" "$archive" "$EMQX_SHA256"
    rm -rf "$target.tmp"
    mkdir -p "$target.tmp"
    tar -xzf "$archive" -C "$target.tmp"
    mv "$target.tmp" "$target"
}

install_influx() {
    local archive="$downloads_dir/$INFLUX_ARCHIVE"
    local target="$runtime_dir/influxdb"
    local extracted="$runtime_dir/influxdb2-$INFLUX_VERSION"
    [ -x "$target/usr/bin/influxd" ] && return 0
    download_verified "$INFLUX_URL" "$archive" "$INFLUX_SHA256"
    rm -rf "$target.tmp" "$extracted"
    tar -xzf "$archive" -C "$runtime_dir"
    mv "$extracted" "$target.tmp"
    mv "$target.tmp" "$target"
}

install_python() {
    local venv="$runtime_dir/venv"
    if [ ! -x "$venv/bin/python" ]; then
        if ! python3 -m venv "$venv"; then
            if command -v apt-get >/dev/null 2>&1; then
                apt-get update
                DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip
                python3 -m venv "$venv"
            else
                echo "python3 venv is unavailable" >&2
                exit 1
            fi
        fi
    fi
    "$venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir --upgrade \
        "pip==25.1.1" "setuptools==80.9.0" "wheel==0.45.1"
    "$venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir \
        -r "$cloud_root/backend/requirements.txt"
    if ! "$venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir \
        --index-url "https://pypi.org/simple" \
        -r "$cloud_root/backend/requirements-llm.txt"; then
        echo "LLM SDK unavailable; fallback advice remains enabled" >&2
    fi
}

main() {
    case "$(uname -s)-$(uname -m)" in
        Linux-x86_64) ;;
        *) echo "unsupported platform: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
    esac
    ensure_dirs
    require_command curl
    require_command tar
    require_command sha256sum
    require_command python3
    install_emqx
    install_influx
    install_python
    chmod +x "$native_root"/*.sh
    echo "native runtime installed"
}

main "$@"
