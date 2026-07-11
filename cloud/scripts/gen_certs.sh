#!/usr/bin/env bash
# 生成 EMQX 自签 TLS 证书 (无域名, 直接绑 IP)
#
# 用法:
#   bash scripts/gen_certs.sh 106.75.229.61
#
# 生成:
#   cloud/emqx/certs/ca.crt      (自签 CA, 客户端做 rootCA 或 insecure=True)
#   cloud/emqx/certs/server.key
#   cloud/emqx/certs/server.crt

set -euo pipefail

IP="${1:-}"
if [ -z "$IP" ]; then
    echo "usage: $0 <public_ip>"
    exit 1
fi

CERT_DIR="$(dirname "$0")/../emqx/certs"
mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

echo "==> 生成自签 CA"
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
    -subj "/C=CN/O=StrokeGuard/CN=StrokeGuard-CA" \
    -out ca.crt

echo "==> 生成 server 私钥 + CSR (SAN=IP:$IP)"
openssl genrsa -out server.key 2048

cat > server.cnf <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions     = v3_req
prompt             = no

[req_distinguished_name]
C  = CN
O  = StrokeGuard
CN = $IP

[v3_req]
keyUsage         = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName   = @alt_names

[alt_names]
IP.1  = $IP
DNS.1 = localhost
EOF

openssl req -new -key server.key -out server.csr -config server.cnf

echo "==> CA 签发 server 证书"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 3650 -sha256 -extensions v3_req -extfile server.cnf

chmod 644 ca.crt server.crt
chmod 600 server.key ca.key

rm -f server.csr ca.srl server.cnf

echo ""
echo "==> 完成. 生成的文件:"
ls -l "$CERT_DIR"
echo ""
echo "==> 客户端 (host_pc) 需要 ca.crt, 复制到:"
echo "    host_pc/certs/emqx_ca.crt"
