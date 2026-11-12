# AgentScope Integration Verification

This directory owns offline and real-service E2E verification. Runnable code
stays under [`../examples`](../examples); cases here import those entry points
and verify registration, discovery, calls, Skill loading, MCP behavior, process
lifecycle and AI log isolation.

```bash
./integration/verify.sh
./integration/verify.sh --only agentscope/a2a
./integration/verify_e2e.sh --only agentscope/mcp/agent
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

Real-service verification uses `python-agentscope-e2e` by default. Provide
`POLARIS_SERVER_ADDRESS`, an optional service token, and the fixtures required
by selected cases. Published, mounted and MCP fixture requirements are checked
before each case starts.

Each case retains artifacts under `integration/cases/<case>/.logs/`. Offline
verification replaces only the Polaris gRPC boundary. Real verification uses
the configured Polaris and Pushgateway endpoints.

See [`test.md`](test.md) for case coverage, environment variables,
artifacts and cleanup scope.

Verification, log and cleanup automation runs exclusively from `integration/`.
