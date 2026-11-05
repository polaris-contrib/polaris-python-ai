# PolarisAgentRuntime

This example composes the Skill loader, A2A registry/resolver, optional MCP
resolver, Core SDK logging and AI category logging through
`PolarisAgentConfig` and `PolarisAgentRuntime`.

```bash
./examples/verify.sh --only agentscope/runtime

python examples/agentscope/runtime/main.py \
  --address 127.0.0.1:8091 \
  --skill-name weather \
  --load-skills
```

Use `--no-skill`, `--no-a2a` and `--mcp` to toggle components. Runtime shutdown
releases adapters and AI logs without destroying the borrowed SDKContext.

The [multi_agent](multi_agent/) example creates two Agents from one Runtime,
shares the Toolkit and Skill snapshot, and keeps their conversation state
isolated.
