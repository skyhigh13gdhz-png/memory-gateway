#!/usr/bin/env bash
set -Eeuo pipefail

HINDSIGHT_BASE_URL="${HINDSIGHT_BASE_URL:-http://127.0.0.1:8888}"
LOCAL_HTTP_PROXY="${MEMORY_GATEWAY_HTTP_PROXY:-http://127.0.0.1:10809}"

ok(){ printf '[✓] %s\n' "$*"; }
warn(){ printf '[!] %s\n' "$*"; }
log(){ printf '[→] %s\n' "$*"; }
die(){ printf '[✗] %s\n' "$*" >&2; exit 1; }

printf '========== Memory Gateway 部署预检 ==========\n'
command -v curl >/dev/null 2>&1 || die '缺少 curl。'
command -v python3 >/dev/null 2>&1 || die '缺少 python3。'
ok '基础命令：curl / python3 已准备'

if curl -fsSIL --max-time 8 https://github.com >/dev/null 2>&1; then
  ok 'GitHub：直连可以访问'
elif curl -fsSIL --max-time 8 --proxy "$LOCAL_HTTP_PROXY" https://github.com >/dev/null 2>&1; then
  ok "GitHub：通过现有本机代理可以访问 (${LOCAL_HTTP_PROXY})"
else
  warn 'GitHub：直连和现有本机代理均不可访问'
fi

if curl -fsSIL --max-time 8 https://gitee.com >/dev/null 2>&1; then
  ok 'Gitee：可以访问'
else
  warn 'Gitee：当前不可访问'
fi

if curl -fsS --max-time 8 "${HINDSIGHT_BASE_URL%/}/docs" >/dev/null 2>&1; then
  ok "Hindsight：可以访问 (${HINDSIGHT_BASE_URL})"
else
  warn "Hindsight：当前不可访问 (${HINDSIGHT_BASE_URL})"
  log '同机部署请确认 Hindsight 已启动；分机部署请检查私网/VPN/HTTPS 地址和防火墙。'
fi

printf '=============================================\n'
