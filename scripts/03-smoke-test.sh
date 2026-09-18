#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${GATEWAY_BASE_URL:-http://127.0.0.1:8787}"
BANK_ID="${GATEWAY_SMOKE_BANK:-gateway-smoke-test}"
TOKEN="${GATEWAY_API_TOKEN:-}"
MARKER="gateway-smoke-$(date +%Y%m%d%H%M%S)"
FACT="部署验收标记 ${MARKER}：Memory Gateway 是 Hindsight 的受控入口层。"
EXPECTED='Memory Gateway 是 Hindsight 的受控入口层'

ok(){ printf '[✓] %s\n' "$*"; }
die(){ printf '[✗] %s\n' "$*" >&2; exit 1; }
[[ -n "$TOKEN" ]] || die '缺少 GATEWAY_API_TOKEN。可先执行 set -a; source .env; set +a'

curl -fsS --max-time 10 "${BASE_URL}/health" >/tmp/gateway-health.json || die 'Gateway /health 不可访问。'
python3 - /tmp/gateway-health.json <<'PY' || die 'Gateway 可访问，但 Hindsight 当前不可达。'
import json,sys
x=json.load(open(sys.argv[1]))
raise SystemExit(0 if x.get('ok') is True else 1)
PY
ok 'Gateway 与 Hindsight 健康链路正常'

json_body(){ python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1]), ensure_ascii=False))' "$1"; }

retain=$(python3 -c 'import json,sys; print(json.dumps({"content":sys.argv[1],"bank_id":sys.argv[2],"client_id":"gateway-smoke","speaker":"liangzai"},ensure_ascii=False))' "$FACT" "$BANK_ID")
curl -fsS --max-time 180 -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' -X POST "${BASE_URL}/v1/memories/retain" -d "$retain" >/tmp/gateway-retain.json || die 'Gateway Retain 失败。'
ok 'Gateway Retain：通过'

recall=$(python3 -c 'import json,sys; print(json.dumps({"query":sys.argv[1],"bank_id":sys.argv[2],"client_id":"gateway-smoke","speaker":"liangzai"},ensure_ascii=False))' "$MARKER" "$BANK_ID")
curl -fsS --max-time 180 -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' -X POST "${BASE_URL}/v1/memories/recall" -d "$recall" >/tmp/gateway-recall.json || die 'Gateway Recall 失败。'
python3 - /tmp/gateway-recall.json "$EXPECTED" <<'PY' || { cat /tmp/gateway-recall.json; die 'Recall 未找回核心事实。'; }
import json,sys
x=json.load(open(sys.argv[1])); expected=sys.argv[2]
texts=[]
def walk(v):
    if isinstance(v,str): texts.append(v)
    elif isinstance(v,dict):
        for z in v.values(): walk(z)
    elif isinstance(v,list):
        for z in v: walk(z)
walk(x)
raise SystemExit(0 if any(expected in t for t in texts) else 1)
PY
ok 'Gateway Recall：通过'

reflect=$(python3 -c 'import json,sys; print(json.dumps({"query":"根据记忆回答：Memory Gateway 相对 Hindsight 是什么角色？请简短回答。","bank_id":sys.argv[1],"client_id":"gateway-smoke","speaker":"liangzai"},ensure_ascii=False))' "$BANK_ID")
curl -fsS --max-time 180 -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' -X POST "${BASE_URL}/v1/memories/reflect" -d "$reflect" >/tmp/gateway-reflect.json || die 'Gateway Reflect 失败。'
python3 - /tmp/gateway-reflect.json <<'PY' || { cat /tmp/gateway-reflect.json; die 'Reflect 返回内容不符合验收语义。'; }
import json,sys
x=json.load(open(sys.argv[1])); texts=[]
def walk(v):
    if isinstance(v,str): texts.append(v)
    elif isinstance(v,dict):
        for z in v.values(): walk(z)
    elif isinstance(v,list):
        for z in v: walk(z)
walk(x); t='\n'.join(texts)
raise SystemExit(0 if 'Memory Gateway' in t and 'Hindsight' in t and ('入口' in t or 'gateway' in t.lower()) else 1)
PY
ok 'Gateway Reflect：通过'

printf '\n========== Gateway 端到端验收 ==========\n'
printf '[✓] Gateway → Hindsight Retain\n'
printf '[✓] Gateway → Hindsight Recall\n'
printf '[✓] Gateway → Hindsight → LLM Reflect\n'
printf '[✓] Bank：%s\n' "$BANK_ID"
printf '结果：Gateway MVP 核心链路正常。\n'
printf '========================================\n'
