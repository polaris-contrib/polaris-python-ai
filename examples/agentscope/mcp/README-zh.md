# MCP Resolver

通过 Polaris 发现健康 MCP Server，生成原生 AgentScope MCP URL，读取服务契约并输出
禁用 Tool。

```bash
python -m examples.agentscope.mcp.main \
  --address 127.0.0.1:8091 --service search-mcp --connect
```

`--connect` 会执行原生 MCP 握手和 `tools/list`；不传时只验证注册中心 metadata 和
契约过滤。
