# AgentScope 集成验证

本目录负责离线和真实服务 E2E 验证。可运行代码保留在
[`../examples`](../examples)，这里只负责 case 编排、fixture、断言、
进程生命周期、日志和清理。

```bash
./integration/verify.sh
./integration/verify.sh --only agentscope/a2a
./integration/verify_e2e.sh --only agentscope/mcp/agent
./integration/verify_e2e.sh --only agentscope/a2a/provider --retain
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

真实验证默认使用 `polaris-python-ai-integration` 命名空间。按所选 case 提供
`POLARIS_SERVER_ADDRESS`、可选服务 token，以及 Published Skill、Mounted Agent
或 MCP fixture。case 启动前会检查自己的前置资源。

每个 case 的产物保存在 `integration/cases/<case>/.logs/`。离线验证只替换
Polaris gRPC 边界；真实验证连接配置的 Polaris 和 Pushgateway。
`--retain` 只用于 A2A Provider，成功后保留独立进程并登记 PID，直到 cleanup。

详细覆盖、环境变量和清理范围见 [`test.md`](test.md)。

验证、日志和清理自动化统一从 `integration/` 执行。
