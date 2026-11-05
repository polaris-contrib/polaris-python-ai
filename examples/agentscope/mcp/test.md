# Verification

Offline:

```bash
../../verify.sh --only agentscope/mcp
```

Real registry:

```bash
../../verify_e2e.sh --only agentscope/mcp
```

The offline check uses real SDK discovery and contract APIs, replacing only the
Polaris gRPC boundary. It verifies the MCP URL, transport, healthy instance and
disabled Tool filtering with a fixed contract. Real verification checks the
resolved URL, transport, healthy instance and the disabled Tool list returned by
the registry; it does not assume a fixture-specific Tool name. `--connect` is not
used by the default verifier because it requires a real MCP HTTP server.

`agentscope/mcp/agent` starts its own MCP Server. It verifies registration,
Polaris discovery, `tools/list`, an actual `echo_text` Tool call, deregistration,
client shutdown, and the local HTTP listener shutdown without an external MCP
fixture.

Logs are retained under `.logs/<run>/console.log`, `result.json`, and
`verification.log`. The resolver scenario requires `POLARIS_MCP_SERVICE`; the
Agent scenario only requires `POLARIS_SERVER_ADDRESS`.
