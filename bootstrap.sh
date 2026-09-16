#!/usr/bin/env bash
set -Eeuo pipefail

GITHUB_REPO="https://github.com/skyhigh13gdhz-png/memory-gateway.git"
GITEE_REPO="https://gitee.com/skyhigh13/memory-gateway.git"
INSTALL_DIR="${MEMORY_GATEWAY_DIR:-/opt/src/memory-gateway}"
LOCAL_HTTP_PROXY="${MEMORY_GATEWAY_HTTP_PROXY:-http://127.0.0.1:10809}"

ok(){ printf '[✓] %s\n' "$*"; }
log(){ printf '\n[→] %s\n' "$*"; }
warn(){ printf '[!] %s\n' "$*"; }
die(){ printf '[✗] %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die '请使用 sudo 运行 bootstrap.sh。'

printf '========== Memory Gateway 一键安装 ==========\n'
log '检查源码网络'
SOURCE_PROXY=""
if curl -fsSIL --max-time 8 https://github.com >/dev/null 2>&1; then
  SOURCE="$GITHUB_REPO"
  ok 'GitHub：直连可用，使用 GitHub Source of Truth'
elif curl -fsSIL --max-time 8 --proxy "$LOCAL_HTTP_PROXY" https://github.com >/dev/null 2>&1; then
  SOURCE="$GITHUB_REPO"
  SOURCE_PROXY="$LOCAL_HTTP_PROXY"
  ok 'GitHub：直连不可用'
  ok "已发现可用的本机海外网络：${LOCAL_HTTP_PROXY}"
  ok 'GitHub：通过现有代理可访问，继续使用 GitHub Source of Truth'
elif curl -fsSIL --max-time 8 https://gitee.com >/dev/null 2>&1; then
  SOURCE="$GITEE_REPO"
  warn 'GitHub 直连和本机代理均不可用，使用 Gitee 只读部署镜像'
else
  die 'GitHub 与 Gitee 当前都不可访问，请先准备可用网络。'
fi

command -v git >/dev/null 2>&1 || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git >/dev/null; }
mkdir -p "$(dirname "$INSTALL_DIR")"

# 仅给本次 Git 操作临时代理，不污染系统、shell 或仓库长期配置。
git_run(){
  if [[ -n "$SOURCE_PROXY" ]]; then git -c "http.proxy=$SOURCE_PROXY" -c "https.proxy=$SOURCE_PROXY" "$@"; else git "$@"; fi
}

if [[ -d "$INSTALL_DIR/.git" ]]; then
  git_run -C "$INSTALL_DIR" fetch "$SOURCE" main
  git -C "$INSTALL_DIR" checkout main >/dev/null 2>&1
  git -C "$INSTALL_DIR" reset --hard FETCH_HEAD >/dev/null
  git -C "$INSTALL_DIR" remote set-url origin "$GITHUB_REPO"
  ok 'Gateway 源码已更新；origin 保持 GitHub'
else
  git_run clone "$SOURCE" "$INSTALL_DIR" >/dev/null
  git -C "$INSTALL_DIR" remote set-url origin "$GITHUB_REPO"
  ok 'Gateway 源码已获取；origin 保持 GitHub'
fi

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  sed -i "s|^GATEWAY_API_TOKEN=.*|GATEWAY_API_TOKEN=${TOKEN}|" "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
  ok '已生成本机 Gateway 访问 Token（仅保存在 .env，不进入 Git）'
fi

set -a; source "$INSTALL_DIR/.env"; set +a
export HINDSIGHT_BASE_URL MEMORY_GATEWAY_HTTP_PROXY="$LOCAL_HTTP_PROXY"
bash "$INSTALL_DIR/scripts/01-preflight.sh"

log '安装并启动 Gateway'
# 安装阶段临时把现有代理传给 apt/pip；Gateway 运行时不会继承这些变量。
if [[ -n "$SOURCE_PROXY" ]]; then
  export http_proxy="$SOURCE_PROXY" https_proxy="$SOURCE_PROXY" HTTP_PROXY="$SOURCE_PROXY" HTTPS_PROXY="$SOURCE_PROXY"
fi
bash "$INSTALL_DIR/scripts/02-install.sh"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY || true

log '执行自动端到端验收'
export GATEWAY_BASE_URL="http://${GATEWAY_HOST:-127.0.0.1}:${GATEWAY_PORT:-8787}"
if bash "$INSTALL_DIR/scripts/03-smoke-test.sh"; then
  ok 'Memory Gateway 核心链路验收通过'
else
  printf '\n[✗] Gateway 已安装，但端到端验收失败。\n' >&2
  printf '[→] 运行 memory-gateway logs 查看日志。\n' >&2
  exit 1
fi

printf '\n========== 安装完成 ==========\n'
printf '日常只需要记住一个命令：memory-gateway\n\n'
printf '  memory-gateway status   查看状态\n'
printf '  memory-gateway health   健康检查\n'
printf '  memory-gateway test     完整记忆验收\n'
printf '  memory-gateway logs     查看日志\n'
printf '  memory-gateway restart  重启服务\n'
printf '  memory-gateway config   查看非敏感配置\n'
printf '==============================\n'
