# AgentScope 示例

支持已发布 Skill、挂载 Skill 和无需模型密钥的 A2A Echo 服务。
依赖安装和统一脚本见 [examples](../README-zh.md)。

`agentscope/a2a/skill` 使用已发布和挂载两种 Skill 运行无模型完整链路：
加载 AgentScope `Agent`，通过 A2A 暴露，发现后完成两轮调用。

`agentscope/mcp` 离线验证 MCP 实例解析和契约过滤。对 MCP 示例增加 `--connect` 后，
会连接真实 MCP Server 并执行 `tools/list`。

`agentscope/runtime` 演示使用 `PolarisAgentConfig` 和 `PolarisAgentRuntime`
统一装配 Skill、A2A、可选 MCP 与 AI 分类日志。

新增场景：

- `a2a/streaming_provider`：每个 A2A context 使用独立 Agent，流式返回 Tool 结果。
- `a2a/console_consumer`：通过 Polaris 发现后进入 AgentScope `launch_console`。
- `a2a/state_resume`：持久化并恢复 `A2AAgentState`。
- `mcp/agent`：启动自包含 MCP Server，注册到 Polaris 并真实调用 Tool。
- `skill/console_agent`：带动态 Skill 刷新的交互式 Agent。
- `runtime/multi_agent`：一个 Runtime 创建两个隔离 Agent，共享 Skill 快照。
- `agent_service`：提供 `/health` 和 `/chat` 的精简 FastAPI Agent 服务。

这些示例使用本地确定性模型，不需要模型 API Key。

```bash
./integration/verify.sh --only agentscope
./integration/verify_e2e.sh --only agentscope
```

所有示例支持 `--config`、`--address`、`--skill-address`、`--namespace`
和 `--timeout`。不传文件时通过环境变量和代码配置启动；
传入 `--address` 时，示例会显式将 Skill 地址设为同主机 `8094`，
也可通过 `--skill-address` 覆盖。
SDK 日志和缓存按运行、组件隔离，关闭扩展不销毁借用的 Context。

手动 A2A Provider 可指定 `--host`、`--port`、`--ttl` 和
`--registration-port`；未指定 host 时使用连接 Polaris 的本机源 IP。
实例默认注册端口为 `1`，真实调用端口保留在 AgentCard interface URL 中。
`--multi-interface` 会在同一端口同时暴露 JSONRPC 和 HTTP+JSON，仍只注册一个实例。
实例 metadata 为 `ai-agent-name`、`ai-agent-card`、`ai-a2a-version`，
`Instance.protocol` 为空。自动心跳复用 ProviderAPI。
Consumer 调用官方 A2AAgent，预期输出 `Echo: Hello Polaris`。
Provider 可用 `--skill-source published|mounted` 切换 Skill 驱动模式，
支持 `/skill-list`、`/skill <name>`，其他输入回显。

已发布 Skill 通过 `--name` 和 `--version` 筛选；挂载 Skill 通过
`--service` 读取服务元数据。临时资源在 loader 关闭时删除。
验证条件与产物记录在 `integration/cases/agentscope/`。
