# A2A Integration

The provider registers a model-free JSON-RPC/SSE Echo endpoint through the
public ProviderAPI; the consumer resolves its AgentCard and invokes the native
AgentScope A2AAgent.

```bash
./examples/verify.sh --only agentscope/a2a
./examples/verify_e2e.sh --only agentscope/a2a
./examples/verify.sh --only agentscope/a2a/skill
./examples/verify.sh --only agentscope/a2a/streaming_provider
./examples/verify.sh --only agentscope/a2a/state_resume
```

The directory also includes a streaming Tool-calling provider, a
`launch_console` consumer, and an `A2AAgentState` resume example.

Real verification needs `POLARIS_SERVER_ADDRESS`; the service token is optional.
It uses a unique service name and a dynamic port, verifies TTL heartbeats,
then deregisters and shuts down the endpoint. See [test.md](test.md).
