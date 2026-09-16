#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
SERVICE_FILE=/etc/systemd/system/memory-gateway.service
CLI_FILE=/usr/local/bin/memory-gateway

ok(){ printf '[✓] %s\n' "$*"; }
die(){ printf '[✗] %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die '请使用 sudo 运行安装脚本。'
[[ -f "${ROOT_DIR}/.env" ]] || die "缺少 ${ROOT_DIR}/.env。"

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv >/dev/null
python3 -m venv "$VENV_DIR"
"${VENV_DIR}/bin/pip" install -q --upgrade pip
"${VENV_DIR}/bin/pip" install -q -r "${ROOT_DIR}/requirements.txt"
ok 'Python 运行环境已准备'

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Memory Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SUDO_USER:-root}
WorkingDirectory=${ROOT_DIR}
EnvironmentFile=${ROOT_DIR}/.env
ExecStart=${VENV_DIR}/bin/uvicorn gateway.main:app --host \${GATEWAY_HOST:-127.0.0.1} --port \${GATEWAY_PORT:-8787}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

install -m 0755 "$ROOT_DIR/bin/memory-gateway" "$CLI_FILE"
# 固定实际安装目录，允许用户通过统一 CLI 管理非默认路径安装。
sed -i "s|^ROOT_DIR=.*|ROOT_DIR=\"${ROOT_DIR}\"|" "$CLI_FILE"
ok '统一管理命令已安装：memory-gateway'

systemctl daemon-reload
systemctl enable --now memory-gateway.service >/dev/null
sleep 2
systemctl is-active --quiet memory-gateway.service || {
  journalctl -u memory-gateway.service -n 50 --no-pager || true
  die 'Memory Gateway 启动失败。'
}
ok 'Memory Gateway 已启动并设置开机自动恢复'
