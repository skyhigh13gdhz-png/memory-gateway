# memory-gateway

个人 AI 外置记忆系统的统一访问网关。

目标是为 ChatGPT、Codex、Claude、Hermes 以及未来其他 AI 客户端提供统一的记忆访问方式，避免上层客户端直接绑定某一个具体记忆引擎。

## 计划能力

- 统一记忆写入接口
- 统一记忆检索接口
- 上下文聚合接口
- Reflection / 总结接口
- Hindsight 适配层
- 鉴权与访问控制
- Raw Store 数据标准化与导入
- 多 AI 客户端接入

## 设计原则

1. **记忆引擎可替换**：上层 AI 不直接依赖 Hindsight 私有 API。
2. **接口稳定优先**：以后即使替换底层 Memory Engine，也尽量不影响客户端。
3. **敏感信息不进入 Git**：API Key、真实服务地址、数据库密码、个人记忆数据等仅保存在运行环境。
4. **与基础设施分离**：服务器部署、Docker、备份等由 `memory-server-infra` 负责，本仓只负责应用/API 层。
5. **中文优先**：文档与运维说明优先使用中文。

## 初步接口方向

```text
POST /memory/remember
POST /memory/search
POST /memory/reflect
GET  /memory/context
```

具体接口会在 Hindsight 基础能力验证完成后再定稿，避免过早设计。

## 当前状态

仓库已初始化，暂不进入开发。

当前优先级是先在 `memory-server-infra` 中完成：

1. Docker + Swap
2. Hindsight 最小部署
3. retain / recall / reflect 验证
4. 持久化与备份恢复

上述基础能力稳定后，再开始本仓的 Gateway 开发。

> 注意：本仓库不存放真实个人记忆数据和任何密钥。
