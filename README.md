<div align="center">
  <h1>Polaris AI Registry for Python</h1>
  <h3>Registration, discovery, and resilient routing for Python AI frameworks.</h3>
</div>

`polaris-python-ai` connects AgentScope, A2A, MCP, and LangGraph applications
to Polaris without replacing the framework execution engine. The repository
publishes one distribution with optional framework extras under the
`polaris_ai` import namespace.

> [!NOTE]
> Polaris complements LangGraph rather than replacing it. Native
> `RemoteGraph` execution remains owned by LangGraph; Polaris provides instance
> registration, health-aware discovery, endpoint selection, failover, and call
> reporting around it.

## Why use polaris-python-ai?

- **One integration surface:** install only the framework extras an application
  needs while keeping one version and import namespace.
- **Registry-backed discovery:** resolve healthy, non-isolated Agent, MCP, and
  LangGraph endpoints instead of hard-coding instance addresses.
- **Resilient remote calls:** preserve endpoint stickiness, refresh discovery,
  and rebuild native clients when an instance changes.
- **Lifecycle support:** register instances, keep heartbeats active, recover from
  missing registrations, and deregister during normal or exceptional shutdown.
- **Operational visibility:** report A2A, MCP, and LangGraph calls while keeping AI
  framework logs separate from Core SDK logs.

## Framework ecosystem

- **Core SDK:** `polaris-python` provides the registration, discovery, Skill, and
  service-contract APIs used by every adapter.
- **AgentScope:** shared contexts, Skill loading, A2A Agents, MCP clients, runtime
  assembly, and dynamic Skill refresh.
- **A2A:** AgentCard registration, discovery, native AgentScope Agents, and
  lifecycle wrappers.
- **MCP:** service-contract filtering, native AgentScope clients, pools, and
  Tool-call reporting.
- **LangGraph:** RemoteGraph registration, graph-aware discovery, sticky routing,
  native client reuse, and invocation metrics.

## Installation

Use Python 3.12 or newer. Run from this project's root directory:

```bash
uv sync --all-extras
uv run python -m pytest
```

The sibling `polaris-python` checkout is selected through `[tool.uv.sources]`;
published wheel metadata contains only version ranges.

Install framework adapters through package extras:

```bash
pip install "polaris-python-ai[a2a]"
pip install "polaris-python-ai[agentscope]"
pip install "polaris-python-ai[langgraph]"
pip install "polaris-python-ai[mcp]"
```

To install every framework adapter:

```bash
pip install "polaris-python-ai[all]"
```

## Documentation

- [Configuration and operation](docs/configuration.md)
- [Versioning, Snapshot, and release](docs/version-release.md)
- [Examples](examples/README.md)
- [AgentScope examples](examples/agentscope/README.md)
- [LangGraph documentation](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph API reference](https://reference.langchain.com/python/langgraph)

See [docs/configuration.md](docs/configuration.md) for the complete feature and
configuration guide, including Core SDK, Skill, A2A, MCP, LangGraph, and AI
logging settings.

AgentScope, A2A, and LangGraph are optional. Base-package imports do not load
their SDKs. The integration targets AgentScope 2.0.10, A2A SDK 1.2.3, and
LangGraph 1.x. Legacy Java AgentCard JSON is decoded through the official A2A
compatibility parser.

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
When `skill.attach_to_agent` is true, `runtime.skill_toolkit` builds a native
Toolkit containing the Polaris loader, and `runtime.create_agent()` attaches that
Toolkit plus the dynamic refresh middleware.

## AI Logging

AI extension logging is optional and disabled for managed files by default. Set
`ai_log_options` on the runtime to enable Polaris-managed category logs:

```python
from polaris_ai import PolarisAILogOptions

runtime = PolarisAgentRuntime(
    config,
    log_options=core_sdk_log_options,
    ai_log_options=PolarisAILogOptions(
        level="info",
        log_dir="./polaris/log/ai",
        max_bytes=50 * 1024 * 1024,
        backup_count=5,
        max_age_days=30,
        warning_throttle_seconds=30,
    ),
)
```

Managed logs are separated from Core SDK logs under `./polaris/log/ai` by
default. Categories are `base`, `agentscope`, `skill`, `a2a`, `mcp`,
`langgraph`, and `metrics`. Each active runtime writes files such as
`base/polaris-ai-base-<clientId>.log`; files are created on first use. Category
files rotate at 50MB, keep five backups, retain backups for 30 days, and use
exclusive file locks.

`POLARIS_AI_LOG_LEVEL` and `POLARIS_AI_LOG_PATH` are used when the corresponding
options are not assigned. `POLARIS_AI_LOG_CAPTURE_AGENTSCOPE=true` optionally
adds an AgentScope `"as"` logger handler for the runtime lifetime. The extension
does not call `agentscope.setup_logger()` or replace existing AgentScope handlers.
Because `"as"` is process-global, only one active runtime can capture it at a time.

The detail policy avoids flooding high-frequency paths:

- `INFO`: runtime lifecycle, Skill reference changes, A2A instance failover and MCP pool changes.
- `DEBUG`: per-page listing, cache hits, candidate filtering, selected endpoints and retries.
- `WARNING`: recoverable failures, deduplicated by key. The default interval is 30 seconds;
  the next emitted warning includes the number of suppressed occurrences.

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
Successful loads with an explicit version are cached by name/version. A blank
version is an active-version alias: it is revalidated and materialized under
the server-returned version. Middleware instances sharing one loader also
share one Toolkit snapshot, so agents created from the same runtime see the
latest successful refresh.
Persistent offline fallback is provided by the SDK, not a second adapter cache.
Published list errors propagate; an individual failed download is logged and
skipped. Empty mount tables are re-read on the next call.
`async_list_skill_names()` refreshes references without downloading ZIPs, and
mounted `async_skill_exists()` checks only the mount table. A `400202` response
raises `PolarisSkillNotFoundError`. The loader exposes `source`, `location`,
`get_repository_info()`, and its read-only identity.

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
5-second TTL. `service_token` is used for registration, heartbeats and
deregistration, is distinct from the connector token, and may be empty when the
server permits unauthenticated registration. The SDK's `bindIP` is not a business
host.

Partial registration failure rolls back only that call's created instances.
Failed deregistrations stay in `registrar.registered`, so another `close()` can
retry. Cancelled registration waits for in-flight SDK work and rolls back its
successes. A closed registrar accepts further cleanup, but no new registrations.
`PolarisA2AServerRegistration` waits for `server_ready` before registration and
deregisters on normal or exceptional exit, replacing the Java Server / Spring
lifecycle assembly.

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
`instance_type="a2a"`; native A2A timeout errors are reported as timeouts.

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

## LangGraph

```python
from polaris_ai.langgraph import (
    LangGraphTransport,
    PolarisLangGraphContext,
    PolarisLangGraphRegistrar,
    PolarisLangGraphResolver,
    PolarisRemoteGraph,
)

with PolarisLangGraphContext.from_address(
    "127.0.0.1:8091",
    "production",
) as polaris, PolarisLangGraphRegistrar(
    polaris.context,
    "production",
) as registrar, PolarisLangGraphResolver(
    polaris.context,
    "production",
) as resolver:
    registrar.register(
        "review-service",
        [LangGraphTransport("10.0.0.8", 8123, "/api", graph_id="review-graph")],
    )
    with PolarisRemoteGraph(
        resolver,
        "review-graph",
        service="review-service",
    ) as graph:
        result = graph.invoke(
            {"messages": []},
            {"configurable": {"thread_id": "thread-1"}},
        )
```

The registrar writes `langgraph.graph-id`, `langgraph.path`, and
`langgraph.protocol` metadata to an ordinary Polaris instance. The resolver
selects a healthy, non-isolated instance for the requested graph, prefers the
previous `host:port`, and reuses the last endpoint when discovery temporarily
fails.

`PolarisRemoteGraph` exposes `invoke`, `ainvoke`, `stream`, and `astream`.
Each call refreshes discovery and reports `instance_type="langgraph"` to Polaris
without changing LangGraph's result or exception. The native `RemoteGraph`
client is reused until the selected URL changes.

`PolarisLangGraphConfig.from_env()` reads `POLARIS_AI_LANGGRAPH_*` first and
accepts `POLARIS_SERVER_ADDRESS`, `POLARIS_TOKEN`,
`POLARIS_SERVICE_TOKEN`, and `POLARIS_NAMESPACE` as fallbacks.

## Validation

```bash
uv run python -m pytest
uv build
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
for manual commands. Real MCP Server E2E, remote controller governance, and
Skill write operations remain outside the current example coverage.
