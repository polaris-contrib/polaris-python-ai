# MCP Agent

This example starts a real MCP streamable HTTP server, registers it in Polaris,
discovers the healthy instance, and invokes its read-only `echo_text` Tool from
an AgentScope `Agent`. The local fixture makes the example runnable without a
pre-existing MCP deployment.

```bash
python -m examples.agentscope.mcp.agent.main \
  --address 127.0.0.1:8091 \
  --namespace python-agentscope-e2e
```
