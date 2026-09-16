#!/usr/bin/env bash
set -Eeuo pipefail

GITHUB_REPO="https://github.com/skyhigh13gdhz-png/memory-gateway.git"
GITEE_REPO="https://gitee.com/skyhigh13/memory-gateway.git"
INSTALL_DIR="${MEMORY_GATEWAY_DIR:-/opt/src/memory-gateway}"

ok(){ printf '[✓] %s\n' "$*"; }
log(){ printf '\n[→] %s\n' "$*"; }
die(){ printf '[✗] %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die '请使用 sudo 运行 bootstrap.sh。'

log '检查源码网络'
if curl -fsSIL --max-time 8 https://github.com >/dev/null 2>&1; then
  SOURCE="$GITHUB_REPO"; ok 'GitHub 可访问，使用 GitHub Source of Truth'
elif curl -fsSIL --max-time 8 https://gitee.com >/dev/null 2>&1; then
  SOURCE="$GITEE_REPO"; ok 'GitHub 当前不可达，使用 Gitee 只读部署镜像'
else
  die 'GitHub 与 Gitee 当前都不可访问，请先准备可用网络。'
fi

command -v git >/dev/null 2>&1 || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git >/dev/null; }
mkdir -p "$(dirname "$INSTALL_DIR")"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  # 不永久修改 origin；GitHub 始终保持唯一 Source of Truth。
  git -C "$INSTALL_DIR" fetch "$SOURCE" main
  git -C "$INSTALL_DIR" checkout main >/dev/null 2>&1
  git -C "$INSTALL_DIR" reset --hard FETCH_HEAD >/dev/null
  ok 'Gateway 源码已更新'
else
  git clone "$SOURCE" "$INSTALL_DIR" >/dev/null
  if [[ "$SOURCE" != "$GITHUB_REPO" ]]; then
    git -C "$INSTALL_DIR" remote set-url origin "$GITHUB_REPO"
  fi
  ok 'Gateway 源码已获取；origin 保持 GitHub'
fi

bash "$INSTALL_DIR/scripts/01-preflight.sh"

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
  printf '\n[!] 已生成 %s/.env\n' "$INSTALL_DIR"
  printf '[!] 请先修改 GATEWAY_API_TOKEN；然后重新运行本 bootstrap。\n'
  printf '[!] 如果 Hindsight 不在本机，同时修改 HINDSIGHT_BASE_URL。\n'
  exit 2
fi

bash "$INSTALL_DIR/scripts/02-install.sh"
ok 'Memory Gateway 部署完成'
printf '\n下一步验收：\n'
printf '  cd %s && set -a && source .env && set +a && sudo -E bash %s/scripts/03-smoke-test.sh\n' "$INSTALL_DIR" "$INSTALL_DIR"
