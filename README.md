# polaris-python-ai

Polaris integrations for Python AI frameworks. The current implementation covers
AgentScope Skill, A2A, MCP, configuration assembly and automatic call reporting
using the public `polaris-python` SDK. Import namespace: `polaris_ai`.

## Development Installation

Use Python 3.12 or newer. Run from this project's root directory:

```bash
uv venv
uv pip install -e ../polaris-python -e '.[agentscope,a2a]' --group dev
```

The SDK version `0.2.0` has not yet been published to PyPI. Until it is published,
use the sibling `polaris-python` checkout configured by `[tool.uv.sources]`. The
declared dependency remains `polaris-python>=0.2.0,<0.3`; after publication, remove
that local source mapping.

AgentScope is optional; `polaris_ai.a2a` is framework-independent. Base-package
imports do not load AgentScope or A2A. The integration targets AgentScope 2.0.10
and A2A SDK 1.2.3. Legacy Java AgentCard JSON is decoded through the official
A2A compatibility parser.

## Shared AgentScope Context

```python
from polaris_ai.agentscope import PolarisAgentContext

with PolarisAgentContext.from_address("127.0.0.1:8091", "default") as polaris:
    provider = polaris.provider
    consumer = polaris.consumer
    skill = polaris.skill
```

The factory owns and closes only the context it creates. It disables stat
reporting and the provider lossless lifecycle, writes the connector token, and
maps every discovery host to the Skill endpoint on port 8094 unless
`skill_address` is explicit. A context passed through `sdk_context` is borrowed
unchanged and is never destroyed by the factory.

Applications that prefer environment-driven assembly can use:

```python
from polaris_ai.agentscope import PolarisAgentConfig, PolarisAgentRuntime

config = PolarisAgentConfig.from_env(agent_name="weather-agent")
async with PolarisAgentRuntime(config) as runtime:
    loader = runtime.skill_loader
    resolver = runtime.resolver
    registrar = runtime.registrar
```

`POLARIS_AI_*` variables take precedence. `POLARIS_SERVER_ADDRESS`,
`POLARIS_TOKEN`, `POLARIS_SERVICE_TOKEN`, and
`POLARIS_SKILL_SERVER_ADDRESS` are accepted as fallbacks. Connector and service
tokens remain separate. Passing an explicit `sdk_context` borrows it and never
changes its configuration or ownership.

## AgentScope Skill Loader

```python
import asyncio
from agentscope.tool import Toolkit
from polaris.api.config import init_context_by_file
from polaris_ai.agentscope import PolarisSkillLoader

async def main():
    context = init_context_by_file("polaris.yaml")
    try:
        async with PolarisSkillLoader(context, namespace="default") as loader:
            toolkit = Toolkit(skills_or_loaders=[loader])
            print(await toolkit.get_skill_instructions())
    finally:
        await asyncio.to_thread(context.destroy)

asyncio.run(main())
```

Published loading uses 50-item pages, at most 100 skills, and a 30-second list
cache. `names=["weather"]` skips listing. `service_name="weather-agent"` loads
only that service's mounted skills. Mount identities are `namespace:skillName`,
split at the first colon; other namespaces are skipped. Version precedence is
mounted version, configured `version`, then the server's active version.

ZIPs include `SKILL.md` and assets. Both flat archives and a single skill folder
are accepted; traversal, absolute paths, links, conflicting entries and multiple
skill roots are rejected. Maximum archive/expanded size is 64 MiB and the entry
limit is 2048. Skills live in temporary directories until the loader closes.
Successful loads are cached by requested name/version; failures are retried.
Persistent offline fallback is provided by the SDK, not a second adapter cache.
Published list errors propagate; an individual failed download is logged and
skipped. Empty mount tables are re-read on the next call.

`list_skills()` follows AgentScope's asynchronous interface. Explicit single-skill
loading is `async_get_skill()`. `close()` and `async_close()` remove temporary assets.

## A2A

```python
from polaris_ai.agentscope import A2ATransport, PolarisA2ARegistrar, PolarisA2AResolver
from agentscope.agent import A2AAgent

# card is the native a2a.types.AgentCard for an already listening server.
async with PolarisA2ARegistrar(context, service_token="service-token") as registrar:
    await registrar.async_register(card, [A2ATransport("10.0.0.1", 8080)])
    async with PolarisA2AResolver(context) as resolver:
        remote_card = await resolver.async_resolve(card.name)
        async with A2AAgent(remote_card) as agent:
            reply = await agent.reply(message)
```

Each transport becomes a Polaris instance. Metadata includes `ai-agent-name`,
`a2a.agent.card`, `a2a.transport` and `a2a.path`; TLS selects `http` or `https`.
Automatic heartbeat and re-registration use the SDK's `register_instance` with a
5-second TTL. `service_token` is required by the current Python Provider API and
is distinct from the connector token. The SDK's `bindIP` is not a business host.

Partial registration failure rolls back only that call's created instances.
Failed deregistrations stay in `registrar.registered`, so another `close()` can
retry. Cancelled registration waits for in-flight SDK work and rolls back its
successes. A closed registrar accepts further cleanup, but no new registrations.

The resolver refreshes discovery on every lookup and stays on the selected
healthy `host:port`. It sees card updates in place and switches when that instance
is unhealthy, isolated, absent or has invalid metadata. Successful empty results
raise `AgentCardNotFoundError`; SDK discovery errors reuse a previously decoded
card. The card's advertised URLs are preserved. Configure each server's card
with its externally reachable endpoints.

`PolarisA2AAgent` wraps the native AgentScope `A2AAgent`. It resolves once,
reuses the client for later turns, and rebuilds it after an explicit
`invalidate()` or a network failure that occurs before any response event is
delivered. Business errors are propagated without switching instances. Streaming
does not retry after an event has already been emitted.

Long-lived Skill-backed Agents can add `PolarisDynamicSkillMiddleware(loader)`.
It refreshes the loader before each reply, honors the loader's refresh interval,
and continues with the last successful state when Polaris is unavailable.

## MCP

```python
from polaris_ai.agentscope import PolarisMCPClientPool, PolarisMCPResolver

resolver = PolarisMCPResolver(context, "default")
client = await resolver.async_create_client("search-mcp")

async with PolarisMCPClientPool(resolver, "search-mcp") as pool:
    selected = pool.choose_client()
```

The resolver reads standard MCP instance metadata, validates the protocol, builds
an AgentScope `HttpMCPConfig`, and maps disabled contract Tools to
`MCPClient.disable_tools`. Streamable HTTP is stateless; SSE is connected as a
stateful client. The pool watches Polaris changes and reconciles clients.
MCP Tool calls automatically report the original Tool name as method and
`instance_type="mcp"`. A2A replies report `message/send` with
`instance_type="a2a"`.

`build_agent_card()` and `PolarisAgentCardTemplate` construct native A2A cards
with protocol, Skills, streaming capability, and input/output modes.

MCP-aware applications can enable the resolver with `POLARIS_AI_MCP_ENABLED=true`
and use `POLARIS_AI_MCP_PROTOCOL_VERSION`, `POLARIS_AI_MCP_SCHEME`,
`POLARIS_AI_MCP_TIMEOUT`, `POLARIS_AI_MCP_HEADERS`,
`POLARIS_AI_MCP_FILTER_CONTRACT`, `POLARIS_AI_MCP_CALLER_SERVICE`, and
`POLARIS_AI_MCP_LABELS`.

Ordinary A2A method names are synchronous; `async_` names are asynchronous.
Skill and A2A adapters borrow `SDKContext`; `PolarisAgentContext` is the only
component that can own one. Close adapters before destroying a shared context.
Configuration remains in `polaris.yaml` or SDK `Configuration` objects; framework
settings are code options.

## Validation

```bash
python -m pytest
python -m build
./examples/verify.sh
./examples/verify.sh --only agentscope/a2a/skill
./examples/verify.sh --only agentscope/mcp
./examples/verify_e2e.sh --only agentscope/a2a
```

Tests use real AgentScope Toolkit and A2A types, public Polaris API wrappers and
a deterministic SDK engine. The A2A transport test exercises the official server
routes, JSON-RPC/SSE and `A2AAgent` through an in-process HTTP transport. These
tests do not constitute a commercial Polaris server integration test.

Offline example verification uses real SDK contexts and AgentScope, replacing
only Polaris RPC calls. Real-registry verification is explicitly enabled through
`verify_e2e.sh`. See [examples/test.md](examples/test.md) for prerequisites,
per-run logs, assertions and cleanup, and [AgentScope examples](examples/agentscope/README.md)
for manual commands.
LangGraph, real MCP Server E2E, remote governance and Skill write operations are
not part of the current AgentScope implementation.
