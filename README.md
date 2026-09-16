# memory-gateway

个人 AI 外置记忆系统的统一访问网关。

目标是为 ChatGPT、Qwen、WorkBuddy、Claude、Hermes、Codex 以及未来其他 AI 客户端提供稳定的记忆访问边界，避免上层客户端直接绑定 Hindsight 或其他具体记忆引擎。

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

## Gateway 负责什么

- 对外提供稳定的 retain / recall / reflect 等统一语义
- 客户端身份、鉴权与访问控制
- client / bank 映射与隔离策略
- Hindsight adapter；未来允许替换或增加其他 memory engine
- 后续接入 Raw Store，并维护 source / metadata 等标准化边界

Gateway **不直接读取 Hindsight 数据库，也不依赖 Hindsight 内部代码**。即使两个组件部署在同一台服务器，也通过 HTTP API 交互。

## 部署原则

Gateway 与 Hindsight **不要求同机**。

同机是个人部署初期最简单、延迟最低的方式：

```text
Gateway → http://127.0.0.1:8888 → Hindsight
```

也支持分机：

```text
Gateway Server → 私网 / VPN / HTTPS → Hindsight Server
```

Hindsight endpoint 始终由运行时配置提供，因此从同机迁移到分机不要求修改 Gateway 业务代码。

Gateway 会拥有自己的统一安装入口。安装器必须自行检查源码/镜像获取、运行环境以及到 Hindsight endpoint 的网络能力；不能假设 `memory-server-infra` 已经替它准备好 Xray。只有实际依赖的目标不可达时才提示网络方案。

## 仓库边界

本仓只负责 Gateway 应用、API、adapter 及其自身部署。Hindsight、Docker、Swap、Hindsight 数据持久化/备份和专属 AI 网络由 `memory-server-infra` 管理。

本仓按可公开源码设计。API Key、OAuth、密码、真实服务凭据、真实个人记忆、数据库、备份和 VLESS 等敏感信息禁止进入 Git；详见 `SECURITY.md`。

GitHub 是唯一可写 Source of Truth；如建立 Gitee 仓库，只作为中国大陆部署镜像，保持 GitHub → Gitee 单向同步。

## 第一阶段接口方向

```text
POST /v1/memories/retain
POST /v1/memories/recall
POST /v1/memories/reflect
GET  /health
```

接口名称先稳定语义，不把 Hindsight 私有参数直接暴露给客户端。具体 request/response contract 在 MVP 中通过 adapter 固化。

## 当前阶段

`memory-server-infra` 已完成 Hindsight 基础部署、网络隔离、cgroup 专属透明代理以及 Retain / Recall / Reflect 功能验收。

现在进入 Gateway MVP：

1. 定义最小稳定 API contract
2. 实现 Hindsight adapter
3. 实现基础 token 鉴权与 client / bank 边界
4. 提供独立 `bootstrap.sh` 与网络/依赖检查
5. 完成 Client → Gateway → Hindsight 端到端 smoke test

后续再接 Raw Store / object storage，不让数据层 schema 阻塞 Gateway 第一阶段闭环。
