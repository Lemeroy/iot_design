#!/usr/bin/env bash

set -euo pipefail

archive="/tmp/strokeguard-cloud-native.tar.gz"
deploy_root="/opt/strokeguard"
cloud_target="$deploy_root/cloud"

[ "$(id -u)" -eq 0 ] || { echo "deploy_remote.sh must run with sudo" >&2; exit 1; }
[ -f "$archive" ] || { echo "missing upload: $archive" >&2; exit 1; }

mkdir -p "$deploy_root"
stage="$(mktemp -d "$deploy_root/deploy.XXXXXX")"
tar -xzf "$archive" -C "$stage"
rm -f "$archive" /tmp/deploy_cloud_native_remote.sh

if [ -d "$cloud_target/native" ]; then
    if [ -f "$cloud_target/native/stop.sh" ]; then
        bash "$cloud_target/native/stop.sh"
    fi
    for name in runtime state logs run downloads; do
        source_path="$cloud_target/native/$name"
        staged_path="$stage/cloud/native/$name"
        if [ -e "$source_path" ]; then
            rm -rf "$staged_path"
            mv "$source_path" "$staged_path"
        fi
    done
fi

if [ -d "$cloud_target" ]; then
    timestamp="$(date +%Y%m%d%H%M%S)"
    mv "$cloud_target" "$deploy_root/cloud.bak.$timestamp"
fi
mv "$stage/cloud" "$cloud_target"
rmdir "$stage"

cd "$cloud_target"
for script in native/*.sh; do
    bash -n "$script"
done
bash native/install.sh
bash native/start.sh
bash native/status.sh
bash native/healthcheck.sh
curl -fsS http://127.0.0.1:8000/health
echo
