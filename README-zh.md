# polaris-python-ai

面向 Python AI 框架的北极星扩展，公开导入名为 `polaris_ai`。当前实现 AgentScope
Skill、A2A、MCP、配置装配和自动调用上报；底层调用 `polaris-python` 公开 API。

## 安装

使用 Python 3.12 或更高版本，在本项目根目录执行：

```bash
uv venv
uv pip install -e ../polaris-python -e '.[agentscope,a2a]' --group dev
```

SDK `0.2.0` 尚未发布到 PyPI，发布前使用 `[tool.uv.sources]` 指向相邻的
`polaris-python` 源码项目。依赖声明保持 `polaris-python>=0.2.0,<0.3`；
发布后可移除本地 source 映射。
AgentScope 和 A2A 为可选依赖，基础包导入不会加载它们。当前验证组合为
AgentScope 2.0.10 和 A2A SDK 1.2.3，A2A 使用官方兼容解析器读取 Java 卡片 JSON。

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

成功下载按名称和请求版本缓存；失败不会缓存。列表失败直接抛错，单个下载失败会记录日志并跳过，
下次重试。空的已发布列表缓存 30 秒，空挂载表下次重新查询。

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
当前 ProviderAPI 要求显式传入 `service_token`，它与 connector token 是两个配置。
业务实例地址由 `A2ATransport.host` 指定，SDK `bindIP` 不作为业务实例 host。

部分注册失败回滚本次成功实例；反注册失败记录保留在 `registered`，可再次 `close()` 重试。
取消注册会等待在途请求完成并回滚，关闭后禁止新注册。

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
`message/send` 和 `instance_type="a2a"` 上报。

`build_agent_card()` 与 `PolarisAgentCardTemplate` 可构造原生 A2A 卡片，支持协议、
Skill、流式能力和输入输出模式。

MCP 应用可通过 `POLARIS_AI_MCP_ENABLED=true` 启用 resolver，并配置
`POLARIS_AI_MCP_PROTOCOL_VERSION`、`POLARIS_AI_MCP_SCHEME`、
`POLARIS_AI_MCP_TIMEOUT`、`POLARIS_AI_MCP_HEADERS`、
`POLARIS_AI_MCP_FILTER_CONTRACT`、`POLARIS_AI_MCP_CALLER_SERVICE` 和
`POLARIS_AI_MCP_LABELS`。

## 验证

```bash
python -m pytest
python -m build
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

LangGraph、真实 MCP Server E2E、远端治理和 Skill 写操作暂不在当前范围。
