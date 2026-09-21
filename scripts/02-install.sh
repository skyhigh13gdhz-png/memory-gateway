#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
SERVICE_FILE=/etc/systemd/system/memory-gateway.service
CLI_FILE=/usr/local/bin/memory-gateway

ok(){ printf '[✓] %s\n' "$*"; }
log(){ printf '[→] %s\n' "$*"; }
die(){ printf '[✗] %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die '请使用 sudo 运行安装脚本。'
[[ -f "${ROOT_DIR}/.env" ]] || die "缺少 ${ROOT_DIR}/.env。"

# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1091
source "${ROOT_DIR}/.env"
set +a
GATEWAY_HOST="${GATEWAY_HOST:-127.0.0.1}"
GATEWAY_PORT="${GATEWAY_PORT:-8787}"
RUN_USER="${SUDO_USER:-root}"
IDEMPOTENCY_DB_PATH="${IDEMPOTENCY_DB_PATH:-/var/lib/memory-gateway/idempotency.sqlite3}"

# Gateway 只依赖 Ubuntu 官方仓中的 Python。服务器上已有的 Docker 等第三方
# apt source 与本组件无关；若它临时不可达，不应让 Gateway 安装输出误导性警告。
# 已安装依赖时完全跳过 apt；缺依赖时仅启用 Ubuntu 官方源完成安装。
if command -v python3 >/dev/null 2>&1 && python3 -c 'import ensurepip' >/dev/null 2>&1; then
  ok '系统 Python / venv 已准备，无需刷新 apt 索引'
else
  log '安装 Python 运行依赖（仅使用 Ubuntu 官方 apt 源）'
  APT_OPTS=(
    -o Dir::Etc::sourcelist=/etc/apt/sources.list
    -o Dir::Etc::sourceparts=-
    -o APT::Get::List-Cleanup=0
  )
  # Ubuntu 24.04 等新版本可能只使用 deb822 /etc/apt/sources.list.d/ubuntu.sources。
  if [[ -f /etc/apt/sources.list.d/ubuntu.sources ]]; then
    APT_OPTS=(
      -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources
      -o Dir::Etc::sourceparts=-
      -o APT::Get::List-Cleanup=0
    )
  fi
  apt-get "${APT_OPTS[@]}" update -qq || die 'Ubuntu 官方软件源更新失败，无法安装 Gateway 运行依赖。'
  DEBIAN_FRONTEND=noninteractive apt-get "${APT_OPTS[@]}" install -y -qq python3 python3-venv >/dev/null || die 'python3/python3-venv 安装失败。'
fi

rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"
"${VENV_DIR}/bin/pip" install -q --upgrade pip
"${VENV_DIR}/bin/pip" install -q -r "${ROOT_DIR}/requirements.txt"
ok 'Python 运行环境已准备'

install -d -m 0750 -o "$RUN_USER" -g "$RUN_USER" "$(dirname "$IDEMPOTENCY_DB_PATH")"
ok "Retain 幂等账本目录已准备：$(dirname "$IDEMPOTENCY_DB_PATH")"

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Memory Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${ROOT_DIR}
EnvironmentFile=${ROOT_DIR}/.env
UMask=0077
ExecStart=${VENV_DIR}/bin/uvicorn gateway.main:app --host ${GATEWAY_HOST} --port ${GATEWAY_PORT}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

install -m 0755 "$ROOT_DIR/bin/memory-gateway" "$CLI_FILE"
sed -i "s|^ROOT_DIR=.*|ROOT_DIR=\"${ROOT_DIR}\"|" "$CLI_FILE"
ok '统一管理命令已安装：memory-gateway'

systemctl daemon-reload
systemctl enable --now memory-gateway.service >/dev/null
systemctl restart memory-gateway.service
sleep 2
systemctl is-active --quiet memory-gateway.service || {
  journalctl -u memory-gateway.service -n 50 --no-pager || true
  die 'Memory Gateway 启动失败。'
}
ok "Memory Gateway 已启动：${GATEWAY_HOST}:${GATEWAY_PORT}，并设置开机自动恢复"
