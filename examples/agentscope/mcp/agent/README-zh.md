# MCP Agent 示例

示例启动真实的 MCP Streamable HTTP Server，将其注册到 Polaris，再通过服务发现
取得健康实例，并在 AgentScope `Agent` 中调用只读 `echo_text` Tool。
本地 fixture 使示例无需预先部署 MCP 服务。

```bash
python -m examples.agentscope.mcp.agent.main \
  --address 127.0.0.1:8091 \
  --namespace python-agentscope-e2e
```
