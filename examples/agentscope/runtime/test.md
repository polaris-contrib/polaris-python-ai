# PolarisAgentRuntime 测试说明

离线验证使用真实 Core SDK Context、AgentScope、Skill loader 和 Runtime，
只替换 Polaris gRPC 边界。

```bash
./examples/verify.sh --only agentscope/runtime
```

验证内容：

- `PolarisAgentConfig` 与借用 `SDKContext`。
- Skill、A2A 和可选 MCP 适配器装配。
- ai_log_options 生成 `polaris/log/ai/base/`、`skill/` 和 `a2a/` 分类日志。
- Runtime 关闭后 AI logger 文件锁释放。
- Runtime 不销毁借用的 Core SDK Context。

每次运行保留 `console.log`、`verification.log` 和 `result.json`，结果 JSON 中包含
AI 分类日志相对路径。

真实注册中心：

```bash
export POLARIS_SERVER_ADDRESS=<host>:8091
export POLARIS_SERVICE_TOKEN=<service-token>
./examples/verify_e2e.sh --only agentscope/runtime
```
