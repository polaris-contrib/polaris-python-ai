# AgentScope Examples

Run commands from the project root after installing `.[agentscope,a2a]` and the
development group. The A2A echo server needs no model API key.

Run all offline integration scenarios with `./integration/verify.sh`, or select
`--only agentscope/a2a` / `--only agentscope/skill`. Real-registry checks use
`./integration/verify_e2e.sh`; prerequisites, retained logs and cleanup commands
are documented in [../test.md](/integration/cases/agentscope/test.md).

`agentscope/a2a/skill` runs the complete model-free chain with both published
and mounted Skills: load an AgentScope `Agent`, expose it through A2A, discover
it, and invoke two turns.

`agentscope/mcp` resolves MCP metadata and contract filtering offline. Add
`--connect` to the MCP example to run a real AgentScope MCP handshake and
`tools/list` against an available server.

`agentscope/runtime` composes Skill, A2A, optional MCP and AI category logging
through `PolarisAgentConfig` and `PolarisAgentRuntime`.

Additional runnable demos:

- `a2a/streaming_provider`: one Agent per A2A context with streamed Tool output.
- `a2a/console_consumer`: Polaris discovery plus AgentScope `launch_console`.
- `a2a/state_resume`: persist and resume `A2AAgentState`.
- `mcp/agent`: self-contained MCP Server, Polaris registration and real Tool call.
- `skill/console_agent`: interactive Agent with dynamically refreshed Skills.
- `runtime/multi_agent`: two isolated Agents sharing one Runtime and Skill snapshot.
- `agent_service`: a small FastAPI `/health` and `/chat` service around an Agent.

These demos use deterministic local models, so they need no model API key.

## Published Skills

```bash
python -m examples.agentscope.skill.published.main --config examples/agentscope/polaris.yaml
python -m examples.agentscope.skill.published.main --address 127.0.0.1:8091 --name weather --version v1
```

The first command lists published skills; the second skips listing. Expected:
Toolkit instructions include skill names and readable temporary asset directories.
Publish the referenced skills in the registry before running.

## Mounted Skills

```bash
python -m examples.agentscope.skill.mounted.main --address 127.0.0.1:8091 --service weather-agent
```

Mount skills on the Agent service in Polaris first. Expected: only mounts in the
selected namespace appear; mounted versions override `--version`.

## A2A Provider and Consumer

```bash
export POLARIS_SERVICE_TOKEN=your-service-token
python -m examples.agentscope.a2a.provider.main --address 127.0.0.1:8091
```

In a second terminal:

```bash
python -m examples.agentscope.a2a.consumer.main --address 127.0.0.1:8091 --message 'Hello Polaris'
```

Expected reply: `Echo: Hello Polaris`. Gracefully stop the provider to exercise
adapter deregistration and SDK heartbeat cleanup. `--host` is the reachable
business address; `--port` defaults to 8080. `--registration-port` defaults to
`1` and is an instance identity, not the callable A2A port. `--multi-interface`
exposes JSONRPC and HTTP+JSON on the same listener while registering one
instance. `--multi-protocol` serves JSONRPC 1.0, JSONRPC 0.3 and HTTP+JSON 1.0
with one instance IP. Real verification with `--retain` keeps the process alive
until integration cleanup. Metadata is `ai-agent-name`, `ai-agent-card`, and `ai-a2a-version`;
the instance protocol remains empty. For authentication, set connector
`POLARIS_TOKEN` independently from `POLARIS_SERVICE_TOKEN`.

Add `--skill-source published --skill-name weather`, or
`--skill-source mounted --skill-service weather-agent`, to expose a Skill-backed
Agent. It answers `/skill-list`, `/skill <name>`, and otherwise echoes the input.

Every example accepts `--config`, `--address`, `--skill-address`, `--timeout`
and `--namespace`. Without a file, SDK defaults and code options are used.
When `--address` is set, examples explicitly inherit the host for the Skill
connector on port `8094` unless `--skill-address` overrides it.

## Local Regression Checks

```bash
python -m pytest tests/test_skill.py tests/test_a2a.py tests/test_a2a_agent.py tests/test_a2a_transport.py
```

These cover pagination, cache versions, mount parsing, ZIP assets, failure retry,
partial registration rollback, sticky discovery, invalid cards, cancellation,
borrowed context lifetime and native AgentScope invocation. A live Polaris
registry and published Skill packages are needed for the preceding examples.
