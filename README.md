# memory-gateway

个人 AI 外置记忆系统的统一访问网关，为 ChatGPT、Qwen、WorkBuddy、Claude、Hermes、Codex 以及未来其他 AI 提供稳定记忆 API，避免客户端直接绑定 Hindsight。

## 先看这里：普通用户只需要两个入口

**首次安装 / 升级：运行仓库根目录 `bootstrap.sh`。** 它负责选择 GitHub/Gitee 源、生成本机 Token、网络与 Hindsight 预检、安装服务、启动并自动执行 Retain / Recall / Reflect 验收。

源码探测使用 `git ls-remote`，所有 Git 操作均有硬超时；已有源码目录如存在未提交修改会明确退出，不会通过 `reset --hard` 静默覆盖。

Python 环境会实际检查 `ensurepip`，因此 Ubuntu 26.04 等系统即使 `python3 -m venv --help` 可用、但缺少 `python3-venv`，安装器也会自动补齐依赖。

在中国大陆服务器，如果已经同步好 Gitee 镜像，可直接：

```bash
curl -fsSL https://gitee.com/skyhigh13/memory-gateway/raw/main/bootstrap.sh | sudo bash
```

GitHub 可达的服务器也可以：

```bash
curl -fsSL https://raw.githubusercontent.com/skyhigh13gdhz-png/memory-gateway/main/bootstrap.sh | sudo bash
```

安装完成后，**日常只需要记住 `memory-gateway`**：

```text
memory-gateway status    查看服务状态
memory-gateway health    检查 Gateway → Hindsight
memory-gateway test      执行 Retain / Recall / Reflect 完整验收
memory-gateway logs      查看最近日志
memory-gateway restart   重启服务
memory-gateway config    查看非敏感配置
memory-gateway help      查看帮助
```

`bootstrap.sh`、`scripts/*` 是安装器内部实现；正常使用不需要逐个执行内部脚本。

> 第一次安装会自动生成随机 Gateway API Token，只保存在服务器本地 `.env`，不会写入 Git。默认认为 Hindsight 在同机 `127.0.0.1:8888`。分机部署时，在安装前准备自己的 `.env` 或安装后修改 `HINDSIGHT_BASE_URL` 并重启 Gateway。

## 架构

```text
ChatGPT / Qwen / WorkBuddy / Claude / Hermes / Codex / future AI
                              ↓
                       Memory Gateway
                              ↓ HTTP API
                         Hindsight
                              ↓
                    持久化 / 备份 / 网络

后续：Gateway → Raw Store / object storage
```

Gateway 负责统一 retain / recall / reflect 语义、鉴权、client/bank 边界以及 memory-engine adapter。它不直接读取 Hindsight 数据库，也不依赖 Hindsight 内部代码。

## 同机与分机

Gateway 与 Hindsight 不要求同机。个人部署初期推荐同机：

```text
Gateway → http://127.0.0.1:8888 → Hindsight
```

也支持：

```text
Gateway Server → 私网 / VPN / HTTPS → Hindsight Server
```

`HINDSIGHT_BASE_URL` 是运行时配置，因此迁移服务器不需要修改 Gateway 业务代码。安装器检查实际需要的网络能力，不把 Xray 或任何具体代理实现写死成 Gateway 架构依赖。

## 对外 API

```text
POST /v1/memories/retain
POST /v1/memories/recall
POST /v1/memories/reflect
GET  /v1/documents
GET  /v1/documents/{document_id}
POST /v1/documents/{document_id}/patch
GET  /health
```

除 `/health` 外均要求 `Authorization: Bearer <Gateway Token>`。客户端只依赖 Gateway contract；Hindsight API 仅存在于 adapter 内。

`memory_retain` 在保持旧客户端兼容的前提下支持可选 `document_id`、`timestamp` 和 `update_mode=replace|append`。Document List/Get 强制用 `speaker:<id>` tag 做范围约束。

Document Patch 是确定性 compare-and-swap：

```json
{
  "speaker": "liangzai",
  "expected_text": "CRV 止损亏损 42 美元。",
  "replacement_text": "CRV 止损亏损 52 美元。",
  "reason": "user_correction"
}
```

- `expected_text` 不存在时返回 `409 PATCH_CONFLICT`；
- 出现多次时返回 `409 PATCH_AMBIGUOUS`；
- 只在精确出现一次时使用同 `document_id` replace；
- 不让 LLM 重写整篇 Document。

Hindsight 0.10.0 实测发现：运行中的异步 reprocess 可在 delete 后重建 Document。因此 Gateway 当前刻意不暴露 delete/reprocess，等操作序列化契约完成后再增加。

## 仓库与安全边界

本仓只负责 Gateway 应用/API/adapter 及其自身部署。Hindsight、Docker、Swap、Hindsight 数据持久化/备份和专属 AI 网络由 `memory-server-infra` 管理。

API Key、OAuth、密码、真实服务凭据、真实个人记忆、数据库、备份和 VLESS 等敏感信息禁止进入 Git，详见 `SECURITY.md`。

GitHub 是唯一可写 Source of Truth；Gitee 只作为中国大陆部署镜像，保持 GitHub → Gitee 单向同步。

## 当前阶段

Gateway V1 Retain/Recall/Reflect 已在正式机通过验收。V2.1 当前增加最薄的 Document/timestamp/Patch 封装，单元测试通过；部署到正式机后仍需在隔离 audit bank 执行端到端验收，再交给 MCP 暴露。

V2.1 正式机隔离 bank 验收入口：

```bash
sudo bash -c 'set -a; source /opt/src/memory-gateway/.env; set +a; python3 /opt/src/memory-gateway/scripts/04-document-smoke-test.py'
```

已验证 Document List/Get、`42 → 52` Patch、重复 Patch `409 PATCH_CONFLICT` 和错误 speaker `404`。
