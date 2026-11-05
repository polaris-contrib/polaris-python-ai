# MCP Agent 测试

```bash
./examples/verify.sh --only agentscope/mcp/agent
./examples/verify_e2e.sh --only agentscope/mcp/agent
```

验证会启动 MCP Server、注册实例、通过 Polaris 发现、创建 AgentScope MCP
Client、列出 Tool 并实际调用 `echo_text`。随后检查反注册、MCP Client 和 HTTP
监听器关闭。

每次运行保留 `console.log`、`verification.log`、`result.json`、SDK 日志与
`polaris/log/ai/mcp/` 分类日志。
