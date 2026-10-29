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
disabled Tool filtering. `--connect` is not used by the default verifier because
it requires a real MCP HTTP server.

Logs are retained under `.logs/<run>/console.log`, `result.json`, and
`verification.log`. Real verification requires `POLARIS_SERVER_ADDRESS` and an
MCP Server registered in the selected namespace.
