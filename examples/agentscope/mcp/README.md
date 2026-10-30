# MCP Resolver

Discover a healthy MCP Server through Polaris, derive the native AgentScope MCP
URL, read the service contract and print disabled Tool names.

```bash
python -m examples.agentscope.mcp.main \
  --address 127.0.0.1:8091 --service search-mcp --connect
```

`--connect` performs the native MCP handshake and `tools/list`. Without it the
example only verifies registry metadata and contract filtering.
