# A2A Integration

The provider registers one instance-level AgentCard through the public
ProviderAPI with registration port `1` by default. The consumer reads
`ai-agent-card` and `ai-a2a-version` from instance metadata and invokes the
native AgentScope A2AAgent. Real endpoints and transports come from the card.

```bash
./integration/verify.sh --only agentscope/a2a
./integration/verify_e2e.sh --only agentscope/a2a
./integration/verify.sh --only agentscope/a2a/skill
./integration/verify.sh --only agentscope/a2a/streaming_provider
./integration/verify.sh --only agentscope/a2a/state_resume
```

The directory also includes a streaming Tool-calling provider, a
`launch_console` consumer, and an `A2AAgentState` resume example.

Use `--registration-port` to override the instance identity port. Parallel
versions on one IP need distinct registration ports.

Real verification needs `POLARIS_SERVER_ADDRESS`; the service token is optional.
It uses a unique service name and a dynamic port, verifies TTL heartbeats,
then deregisters and shuts down the endpoint. See [test.md](/integration/cases/agentscope/a2a/test.md).
