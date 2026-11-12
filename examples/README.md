# Examples

This directory contains runnable AgentScope integration examples. The files
here are executable documentation for application authors; verification
orchestration, registry stubs, assertions and fixture cleanup live under
[`../integration`](../integration).

Install Python 3.12+ and the example dependencies:

```bash
uv sync --all-extras
```

Run examples directly:

```bash
python -m examples.agentscope.a2a.provider.main --address 127.0.0.1:8091
python -m examples.agentscope.a2a.consumer.main --address 127.0.0.1:8091
python -m examples.agentscope.skill.published.main --address 127.0.0.1:8091
python -m examples.agentscope.mcp.agent.main --address 127.0.0.1:8091
python -m examples.agentscope.agent_service.main --address 127.0.0.1:8091
```

Each runnable directory also exposes `build`, `run`, `package` and `clean`
through its Makefile:

```bash
make -C examples/agentscope/a2a/provider run ARGS="--address 127.0.0.1:8091"
make -C examples/agentscope/mcp/agent run ARGS="--address 127.0.0.1:8091"
```

Example groups:

- A2A provider and consumer, including streaming, state resume and Skill-backed agents.
- MCP metadata resolution and a self-contained MCP Agent with a real Tool call.
- Published, mounted and console Skill experiences.
- Runtime composition with one or multiple Agents.
- A small FastAPI Agent service with `/health` and `/chat`.

Offline and real-service verification commands are documented in
[`integration/README.md`](../integration/README.md). Verification, log and
cleanup commands run exclusively from `integration/`.
