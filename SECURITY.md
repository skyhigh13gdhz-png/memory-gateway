# 安全边界

`memory-gateway` 按可公开源码仓库设计。

## 禁止提交

- API Key、OAuth 凭据、访问 Token、密码、私钥、证书私钥
- 真实 Hindsight / PostgreSQL / Raw Store 的公网或私有凭据
- 真实个人记忆、对话、日记、附件、备份和数据库文件
- VLESS 或其他代理节点凭据
- 任何生产环境 `.env`

## 可以提交

- `.env.example` 等无真实凭据的模板
- Gateway API contract、adapter、鉴权框架和 bank policy 代码
- 使用虚构数据的测试
- 部署脚本与网络能力检测脚本

## 部署原则

Gateway 与 Hindsight 不要求同机。两者即使同机也只通过 Hindsight API 交互，不直接读取 Hindsight 数据库或导入其内部代码。

Hindsight 地址必须由运行时配置提供。同机可使用 `127.0.0.1`；分机应优先使用私网、VPN 或受 TLS 保护的地址，不应为了方便直接把 Hindsight API 裸露到公网。

Gateway 的安装脚本只检查自己真正依赖的网络能力，不把 Xray 或任何具体代理实现写死为架构依赖。
