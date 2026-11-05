# PolarisAgentRuntime 测试说明

离线验证使用真实 Core SDK Context、AgentScope、Skill loader 和 Runtime，
只替换 Polaris gRPC 边界。

```bash
./examples/verify.sh --only agentscope/runtime
./examples/verify.sh --only agentscope/runtime/multi_agent
```

验证内容：

- `PolarisAgentConfig` 与借用 `SDKContext`。
- Skill、A2A 和可选 MCP 适配器装配。
- ai_log_options 生成 `polaris/log/ai/base/`、`skill/` 和 `a2a/` 分类日志。
- Runtime 关闭后 AI logger 文件锁释放。
- Runtime 不销毁借用的 Core SDK Context。
- 一个 Runtime 创建两个 Agent，共享 Toolkit/snapshot，且会话状态隔离。

每次运行保留 `console.log`、`verification.log` 和 `result.json`，结果 JSON 中包含
AI 分类日志相对路径。

真实注册中心：

```bash
export POLARIS_SERVER_ADDRESS=<host>:8091
./examples/verify_e2e.sh --only agentscope/runtime
```

真实 Skill 名称未显式设置时，验证器会从目标命名空间自动选择第一个
已发布 Skill。
