<div align="center">
  <h1>Polaris AI Registry for Python</h1>
  <h3>面向 Python AI 框架的注册发现与弹性路由集成。</h3>
</div>

`polaris-python-ai` 将 AgentScope、A2A、MCP 和 LangGraph 应用接入北极星，
但不替代框架原有的执行引擎。本仓库只发布一个 distribution，通过可选 extras
提供各框架适配，公开导入名统一为 `polaris_ai`。

> [!NOTE]
> Polaris 与 LangGraph 是互补关系。原生 `RemoteGraph` 的执行仍由 LangGraph
> 负责；Polaris 为其提供实例注册、健康感知发现、端点选择、故障切换和调用上报。

## 为什么使用 polaris-python-ai

- **统一接入入口**：按应用需要安装框架 extras，同时共享同一个版本号和导入命名空间。
- **注册中心发现**：通过 Polaris 获取健康、未隔离的 Agent、MCP 和 LangGraph 端点，
  无需硬编码实例地址。
- **弹性远程调用**：保持端点粘性、刷新发现结果，并在实例变化后重建原生客户端。
- **完整生命周期**：支持实例注册、自动心跳、实例缺失重注册，以及正常或异常退出时反注册。
- **可观测性**：上报 A2A、MCP 和 LangGraph 调用，并将 AI 框架日志与 Core SDK 日志分离。

## 框架生态

- **Core SDK**：`polaris-python` 提供注册、发现、Skill 和服务契约等底层能力。
- **AgentScope**：共享 Context、Skill 加载、A2A Agent、MCP Client、Runtime 装配和动态刷新。
- **A2A**：AgentCard 注册发现、原生 AgentScope Agent 和生命周期封装。
- **MCP**：服务契约过滤、原生 AgentScope Client、连接池和 Tool 调用上报。
- **LangGraph**：RemoteGraph 注册、Graph 感知发现、粘性路由、原生客户端复用和调用指标。

## 安装

使用 Python 3.12 或更高版本，在本项目根目录执行：

```bash
uv sync --all-extras
uv run python -m pytest
```

相邻 `polaris-python` 通过 `[tool.uv.sources]` 参与本地解析；发布 wheel
只声明版本范围。

通过 extras 安装对应适配器：

```bash
pip install "polaris-python-ai[a2a]"
pip install "polaris-python-ai[agentscope]"
pip install "polaris-python-ai[langgraph]"
pip install "polaris-python-ai[mcp]"
```

安装全部框架适配：

```bash
pip install "polaris-python-ai[all]"
```

## 文档

- [功能与配置](docs/configuration.md)
- [版本、Snapshot 与发布](docs/version-release.md)
- [示例索引](examples/README-zh.md)
- [AgentScope 示例](examples/agentscope/README-zh.md)
- [LangGraph 官方文档](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph API 参考](https://reference.langchain.com/python/langgraph)

完整功能与配置见 [docs/configuration.md](docs/configuration.md)，包含 Core SDK、
Skill、A2A、MCP、LangGraph 和 AI 日志配置。

AgentScope、A2A 和 LangGraph 为可选依赖，基础包导入不会加载它们。当前验证组合为
AgentScope 2.0.10、A2A SDK 1.2.3 和 LangGraph 1.x，A2A 使用官方兼容解析器读取
Java 卡片 JSON。

## 共享 AgentScope Context

```python
from polaris_ai.agentscope import PolarisAgentContext

with PolarisAgentContext.from_address("127.0.0.1:8091", "default") as polaris:
    provider = polaris.provider
    consumer = polaris.consumer
    skill = polaris.skill
```

工厂只拥有并关闭自己创建的 context。它会关闭 stat 上报、写入 connector token，
并关闭 provider 无损上下线，然后把每个发现地址的 host 映射到 8094 端口的 Skill
地址；显式 `skill_address` 优先。通过 `sdk_context` 传入的 context 保持原配置，
且不会被工厂销毁。

应用侧也可以使用环境变量装配：

```python
from polaris_ai.agentscope import PolarisAgentConfig, PolarisAgentRuntime

config = PolarisAgentConfig.from_env(agent_name="weather-agent")
async with PolarisAgentRuntime(config) as runtime:
    loader = runtime.skill_loader
    resolver = runtime.resolver
    registrar = runtime.registrar
```

`POLARIS_AI_*` 变量优先；`POLARIS_SERVER_ADDRESS`、`POLARIS_TOKEN`、
`POLARIS_SERVICE_TOKEN` 和 `POLARIS_SKILL_SERVER_ADDRESS` 作为回退。connector
token 与 service token 保持分离。显式传入 `sdk_context` 时只借用，不改配置、
不接管生命周期。
`skill.attach_to_agent` 为 true 时，`runtime.skill_toolkit` 会创建包含 Polaris
loader 的原生 Toolkit；`runtime.create_agent()` 会同时接入 Toolkit 和动态刷新
Middleware。

## AI 日志

AI 扩展默认不创建 Polaris 管理的日志文件。需要由 Runtime 管理分类日志时，
传入独立的 `ai_log_options`：

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

默认与 Core SDK 日志分开存放在 `./polaris/log/ai`。分类为 `base`、
`agentscope`、`skill`、`a2a`、`mcp`、`langgraph` 和 `metrics`，文件按首次使用创建，例如
`base/polaris-ai-base-<clientId>.log`。每类默认 50MB 滚动、保留 5 份和 30 天，
并使用跨进程独占文件锁。

代码未显式赋值的 level 和 path 会读取 `POLARIS_AI_LOG_LEVEL`、
`POLARIS_AI_LOG_PATH`。`POLARIS_AI_LOG_CAPTURE_AGENTSCOPE=true` 可以在 Runtime
生命周期内桥接 AgentScope `"as"` logger，但不会调用 `agentscope.setup_logger()`
或替换 AgentScope 原有 handler。由于 `"as"` 是进程级 logger，同一进程同一时刻只能
有一个活动 Runtime 捕获它。

详细程度策略：

- `INFO`：Runtime 生命周期、Skill 引用变化、A2A 实例切换和 MCP 池成员变化。
- `DEBUG`：分页、缓存命中、候选过滤、选中地址和重试等高频细节。
- `WARNING`：可恢复错误按 key 聚合，默认 30 秒内只输出一次；下一次输出会带上被抑制次数。

## Skill 加载

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

默认每页 50 条，最多加载 100 个，列表缓存 30 秒。指定 `names=["weather"]`
直接下载，跳过列表；指定 `service_name="weather-agent"` 只加载该服务挂载的 Skill。
挂载名称 `namespace:skillName` 按第一个冒号切分，其他命名空间跳过，重复名称保留第一条。
版本优先级为挂载版本、构造时指定的 `version`、服务端 active 版本。

显式版本下载成功后按名称和版本缓存；空版本表示服务端 active 版本，会重新验证，并按服务端
返回的实际版本物化缓存。共享同一个 loader 的多个动态刷新中间件共享一份 Toolkit 快照，
同一 Runtime 创建的多个 Agent 都会看到最新成功刷新。
失败不会缓存。列表失败直接抛错，单个下载失败会记录日志并跳过，下次重试。空的已发布列表缓存
30 秒，空挂载表下次重新查询。
`async_list_skill_names()` 只刷新引用列表，不下载 ZIP；挂载模式的
`async_skill_exists()` 只检查挂载表。服务端返回 `400202` 时抛
`PolarisSkillNotFoundError`。loader 暴露 `source`、`location`、
`get_repository_info()` 和只读标识。

下载 ZIP 中的 `SKILL.md` 和资源解压到临时目录，支持平铺或单一顶层 Skill 目录。
拒绝越界 / 绝对路径、链接、冲突文件和多 Skill 根目录，压缩与解压大小上限 64 MiB，
最多 2048 项。`close()` / `async_close()` 清理临时资源；持久化和网络故障降级由 SDK 负责。
`list_skills()` 遵循 AgentScope 原生异步接口，单个 Skill 使用 `async_get_skill()`。

## A2A 注册与发现

```python
from agentscope.agent import A2AAgent
from polaris_ai.agentscope import A2ATransport, PolarisA2ARegistrar, PolarisA2AResolver

# card 为已启动服务的 a2a.types.AgentCard；message 为 AgentScope 消息。
async with PolarisA2ARegistrar(context, service_token="service-token") as registrar:
    await registrar.async_register(card, [A2ATransport("10.0.0.1", 8080)])
    async with PolarisA2AResolver(context) as resolver:
        remote_card = await resolver.async_resolve(card.name)
        async with A2AAgent(remote_card) as agent:
            reply = await agent.reply(message)
```

每个 transport 注册一个普通实例，写入 `ai-agent-name`、`a2a.agent.card`、
`a2a.transport` 和 `a2a.path`。自动心跳和实例不存在重注册复用 SDK，TTL 默认 5 秒。
`service_token` 用于注册、心跳和反注册，它与 connector token 是两个配置；可为空，
由服务端决定是否接受无鉴权注册。
业务实例地址由 `A2ATransport.host` 指定，SDK `bindIP` 不作为业务实例 host。

部分注册失败回滚本次成功实例；反注册失败记录保留在 `registered`，可再次 `close()` 重试。
取消注册会等待在途请求完成并回滚，关闭后禁止新注册。
`PolarisA2AServerRegistration` 可等待 `server_ready` 事件后再注册，退出或异常时
统一反注册，用于替代 Java Server / Spring 的生命周期装配。

每次解析重新发现，按健康 `host:port` 保持粘性并读取最新卡片；实例移除、不健康、隔离或
卡片失效后切换。SDK 查询异常时复用此前成功卡片；成功空结果抛 `AgentCardNotFoundError`。
保留卡片声明的 URL，服务端需提供真实可访问的地址。

A2A 普通名称为同步接口，`async_` 前缀为异步接口；通用 A2A 入口也可从 `polaris_ai.a2a`
导入。Skill 与 A2A 适配器借用 `SDKContext`，只有 `PolarisAgentContext` 可以拥有
context。关闭时只释放自身资源，应用统一销毁共享 context。
SDK 配置继续使用 `polaris.yaml` 或 `Configuration`，框架参数通过代码指定。

`PolarisA2AAgent` 包装原生 AgentScope `A2AAgent`：首次调用解析卡片，后续轮次复用
客户端；显式 `invalidate()` 或尚未输出任何事件的网络错误会重新解析并重建客户端。
业务错误直接抛出，不切换实例；流式调用已经输出事件后不会重试。

长生命周期 Skill Agent 可加入 `PolarisDynamicSkillMiddleware(loader)`。它会在每轮
回复前刷新 loader，遵循刷新间隔；Polaris 不可用时记录警告并继续使用最近一次成功状态。

## MCP

```python
from polaris_ai.agentscope import PolarisMCPClientPool, PolarisMCPResolver

resolver = PolarisMCPResolver(context, "default")
client = await resolver.async_create_client("search-mcp")

async with PolarisMCPClientPool(resolver, "search-mcp") as pool:
    selected = pool.choose_client()
```

Resolver 读取标准 MCP 实例 metadata、校验协议、构造 AgentScope `HttpMCPConfig`，
并把契约中禁用的 Tool 写入 `MCPClient.disable_tools`。Streamable HTTP 使用无状态
客户端，SSE 使用有状态连接。连接池通过 watch 感知实例增删并同步重建客户端。
MCP Tool 调用自动以原 Tool 名作为 method、`instance_type="mcp"` 上报；A2A 回复自动以
`message/send` 和 `instance_type="a2a"` 上报，官方 A2A 超时异常会按 timeout 上报。

`build_agent_card()` 与 `PolarisAgentCardTemplate` 可构造原生 A2A 卡片，支持协议、
Skill、流式能力和输入输出模式。

MCP 应用可通过 `POLARIS_AI_MCP_ENABLED=true` 启用 resolver，并配置
`POLARIS_AI_MCP_PROTOCOL_VERSION`、`POLARIS_AI_MCP_SCHEME`、
`POLARIS_AI_MCP_TIMEOUT`、`POLARIS_AI_MCP_HEADERS`、
`POLARIS_AI_MCP_FILTER_CONTRACT`、`POLARIS_AI_MCP_CALLER_SERVICE` 和
`POLARIS_AI_MCP_LABELS`。

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

注册器把 `langgraph.graph-id`、`langgraph.path` 和 `langgraph.protocol` 写入普通
Polaris 实例。Resolver 只选择对应 graph 的健康、未隔离实例，优先复用上次
`host:port`；发现临时失败时复用最近一次成功端点。

`PolarisRemoteGraph` 提供 `invoke`、`ainvoke`、`stream` 和 `astream`。每次调用都会
刷新发现，并以 `instance_type="langgraph"` 上报结果，不改变 LangGraph 的返回值或
异常。原生 `RemoteGraph` 客户端在 URL 不变时复用，切换实例后重建。

`PolarisLangGraphConfig.from_env()` 优先读取 `POLARIS_AI_LANGGRAPH_*`，并接受
`POLARIS_SERVER_ADDRESS`、`POLARIS_TOKEN`、`POLARIS_SERVICE_TOKEN` 和
`POLARIS_NAMESPACE` 作为回退。

## 验证

```bash
uv run python -m pytest
uv build
./examples/verify.sh
./examples/verify.sh --only agentscope/a2a/skill
./examples/verify.sh --only agentscope/mcp
./examples/verify_e2e.sh --only agentscope/a2a
```

已验证原生 Toolkit、官方 A2A 类型、公开 SDK 包装器，以及本地 JSON-RPC/SSE 调用。
单元测试使用确定性 SDK 替身。examples 离线集成测试使用真实 SDK 和 AgentScope，
仅替换 Polaris gRPC 边界；真实注册中心验证由 verify_e2e.sh 显式运行。
运行参数、前置资源、日志和清理见 [examples/test.md](examples/test.md)。
可运行的已发布 Skill、挂载 Skill、A2A provider / consumer 和 Skill 驱动 A2A 示例见
[examples/agentscope](examples/agentscope/README.md)，A2A Echo 示例无需模型密钥。
真实 MCP Server E2E、远端 Controller 治理和 Skill 写操作暂不在当前范围。
