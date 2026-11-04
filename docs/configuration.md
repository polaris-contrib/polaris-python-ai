# polaris-python-ai 功能与完整配置指引

本文面向应用开发者，说明 `polaris-python-ai` 当前支持的功能、配置层级、全部应用侧参数、
环境变量和日志行为。

## 1. 配置分层

项目有三层独立配置：

| 层级 | 配置入口 | 负责内容 |
| --- | --- | --- |
| Core SDK | `polaris.yaml` / `Configuration` / `log_options` | 注册中心连接、TLS、超时、缓存、Core SDK 分类日志 |
| AI 应用 | `PolarisAgentConfig` / `PolarisAgentRuntime` | Skill、A2A、MCP 和 AgentScope 装配 |
| AI 日志 | `PolarisAILogOptions` / `ai_log_options` | AI 扩展自己的分类日志文件 |

这些配置不会互相合并：

- AgentScope、Skill、A2A、MCP 参数不写入 `polaris.yaml`。
- AI 日志不读取 Core SDK 的 `POLARIS_LOG_LEVEL`、`POLARIS_LOG_PATH`。
- Core SDK 的 `log_options` 和 AI 扩展的 `ai_log_options` 是两个参数。
- 通过 `sdk_context` 传入已有 Context 时，该 Context 被视为借用对象，不会被 Runtime 修改或销毁。

## 2. 快速开始

```python
from polaris_ai.agentscope import PolarisAgentConfig, PolarisAgentRuntime

config = PolarisAgentConfig(
    namespace="default",
    addresses=("127.0.0.1:8091",),
    connector_token="",
    service_token="",
)

async with PolarisAgentRuntime(config) as runtime:
    loader = runtime.skill_loader
    resolver = runtime.resolver
    registrar = runtime.registrar
    mcp_resolver = runtime.mcp_resolver
```

默认行为：

- 已发布 Skill 加载启用。
- A2A 注册和发现启用。
- MCP 解析禁用。
- AI 文件日志禁用，继续使用应用 Python logging 配置。

## 3. Core SDK 配置

Core SDK 继续使用 `polaris-python` 的 `polaris.yaml`、`Configuration` 和
`LogOptions`。AI 扩展不复制这些配置模型。

最小 `polaris.yaml`：

```yaml
global:
  serverConnector:
    addresses:
      - ${POLARIS_SERVER_ADDRESS:127.0.0.1:8091}
    token: ${POLARIS_TOKEN:}
  api:
    timeout: 5s
  statReporter:
    enable: false
```

使用已有 Context：

```python
from polaris.api.config import init_context_by_file
from polaris_ai.agentscope import PolarisAgentConfig, PolarisAgentRuntime

sdk_context = init_context_by_file("polaris.yaml")
runtime = PolarisAgentRuntime(
    PolarisAgentConfig(
        namespace="default",
        addresses=("ignored-when-context-is-borrowed:8091",),
    ),
    sdk_context=sdk_context,
)
```

借用 Context 时，Runtime 不读取或修改其连接、TLS、缓存和 Core SDK 日志配置。应用负责最终销毁
`sdk_context`。

Core SDK `LogOptions` 字段：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `level` | 环境变量或 `info` | `debug/info/warn/error` |
| `file_path` | 无 | 显式基础文件名 |
| `log_dir` | `./polaris/log` | Core SDK 日志根目录 |
| `max_bytes` | 50MB | 单文件滚动大小 |
| `backup_count` | 5 | 编号备份数量 |
| `max_age_days` | 30 | 备份保留天数，0 关闭年龄清理 |

Core SDK 的 `file_path` 和 `log_dir` 互斥。详细 YAML、TLS、缓存和日志配置以
`polaris-python` 项目文档为准。

## 4. PolarisAgentRuntime 配置

```python
PolarisAgentRuntime(
    config: PolarisAgentConfig,
    *,
    sdk_context=None,
    log_options: LogOptions | None = None,
    ai_log_options: PolarisAILogOptions | None = None,
)
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `config` | 是 | AI 应用配置 |
| `sdk_context` | 否 | 借用已有 Core SDK Context |
| `log_options` | 否 | 自建 Core SDK Context 时使用的 Core 日志配置 |
| `ai_log_options` | 否 | 启用 AI 扩展分类文件日志 |

生命周期：

- Runtime 拥有自己创建的 Context，并负责关闭。
- Runtime 借用 `sdk_context` 时只关闭 Skill、A2A、MCP 和日志资源，不销毁 Context。
- Runtime 关闭后不能再创建 Agent 或使用已关闭适配器。

## 5. 应用总配置

`PolarisAgentConfig` 位于 `polaris_ai.agentscope.config`。

| 字段 | 默认值 | 环境变量 | 说明 |
| --- | --- | --- | --- |
| `enabled` | `True` | `POLARIS_AI_ENABLED` | 关闭后 Runtime 拒绝启动 |
| `namespace` | `default` | `POLARIS_AI_NAMESPACE` | 注册发现和 Skill 命名空间 |
| `addresses` | `("127.0.0.1:8091",)` | `POLARIS_AI_ADDRESS` / `POLARIS_AI_ADDRESSES` | 注册中心地址，逗号分隔 |
| `connector_token` | 空 | `POLARIS_AI_CONNECTOR_TOKEN` | SDK 接入鉴权 token |
| `service_token` | 空 | `POLARIS_AI_SERVICE_TOKEN` | 注册、心跳和反注册服务 token |
| `skill` | 默认对象 | - | Skill 子配置 |
| `a2a` | 默认对象 | - | A2A 子配置 |
| `mcp` | 默认对象 | - | MCP 子配置 |

`from_env()` 的旧变量回退：

| 新变量 | 回退变量 |
| --- | --- |
| `POLARIS_AI_ADDRESS` / `POLARIS_AI_ADDRESSES` | `POLARIS_SERVER_ADDRESS` / `POLARIS_SERVER_ADDRESSES` |
| `POLARIS_AI_CONNECTOR_TOKEN` | `POLARIS_TOKEN` |
| `POLARIS_AI_SERVICE_TOKEN` | `POLARIS_SERVICE_TOKEN` |
| `POLARIS_AI_SKILL_ADDRESS` | `POLARIS_SKILL_SERVER_ADDRESS` |

`POLARIS_AI_*` 优先于旧变量。直接构造 `PolarisAgentConfig` 不读取环境变量；只有调用
`PolarisAgentConfig.from_env()` 时才按上表解析。

```python
from polaris_ai.agentscope import PolarisAgentConfig
from polaris_ai.agentscope.config import (
    PolarisA2AConfig,
    PolarisA2ADiscoveryConfig,
    PolarisA2ARegistryConfig,
    PolarisMCPConfig,
    PolarisSkillConfig,
)

config = PolarisAgentConfig(
    namespace="production",
    addresses=("polaris-a:8091", "polaris-b:8091"),
    connector_token="connector-token",
    service_token="service-token",
    skill=PolarisSkillConfig(
        names=("weather",),
        version="",
        attach_to_agent=True,
    ),
    a2a=PolarisA2AConfig(
        registry=PolarisA2ARegistryConfig(ttl=5),
        discovery=PolarisA2ADiscoveryConfig(enabled=True),
    ),
    mcp=PolarisMCPConfig(
        enabled=True,
        scheme="https",
        timeout=10,
    ),
)
```

布尔环境变量支持：

```text
true false 1 0 yes no on off
```

## 6. Skill 配置

`PolarisSkillConfig` 位于 `PolarisAgentConfig.skill`。

| 字段 | 默认值 | 环境变量 | 说明 |
| --- | --- | --- | --- |
| `enabled` | `True` | `POLARIS_AI_SKILL_ENABLED` | 启用 Skill loader |
| `addresses` | 空 | `POLARIS_AI_SKILL_ADDRESS` | SkillAPI 地址；为空时由发现地址推导 8094 端口 |
| `names` | 空 | `POLARIS_AI_SKILL_NAMES` | 指定 Skill 名称，逗号分隔；非空时跳过列表 |
| `version` | 空 | `POLARIS_AI_SKILL_VERSION` | 固定版本；空表示服务端 active 版本 |
| `list_limit` | `50` | `POLARIS_AI_SKILL_LIST_LIMIT` | 分页大小，必须大于 0 |
| `max_skills` | `100` | `POLARIS_AI_SKILL_MAX_SKILLS` | 最大加载数量，必须大于 0 |
| `refresh_interval` | `30.0` | `POLARIS_AI_SKILL_LIST_REFRESH_INTERVAL_SECONDS` | 列表缓存秒数，0 表示不缓存 |
| `mounted_enabled` | `False` | `POLARIS_AI_MOUNTED_SKILL_ENABLED` | 只读取服务挂载的 Skill |
| `mounted_service_name` | 空 | `POLARIS_AI_MOUNTED_SKILL_SERVICE` | 挂载服务名 |
| `attach_to_agent` | `True` | `POLARIS_AI_SKILL_ATTACH_TO_AGENT` | Runtime 创建 Agent 时挂载 Skill Toolkit 和刷新中间件 |

挂载服务名在 `from_env()` 中按以下顺序回退：

```text
POLARIS_AI_MOUNTED_SKILL_SERVICE
POLARIS_AI_A2A_CARD_NAME
POLARIS_AI_AGENT_NAME
from_env(agent_name=...)
```

`names` 与 `mounted_enabled` 不能同时使用。

Skill 行为：

- 已发布 Skill 按 namespace 分页读取。
- 挂载 Skill 读取服务 `extended_metadata`。
- 挂载名按第一个冒号解析为 `namespace:skillName`。
- 版本优先级：挂载版本、配置版本、服务端 active 版本。
- 固定版本按 `(name, version)` 缓存。
- 空版本每次重新确认 active 版本，并按服务端返回实际版本物化缓存。
- ZIP 支持平铺或单一顶层目录，限制 64MiB、2048 项，拒绝路径越界、链接和重复条目。
- Skill 写、删除和上传不支持。

## 7. A2A 配置

### 7.1 A2A 总开关

`PolarisA2AConfig` 位于 `PolarisAgentConfig.a2a`。

| 字段 | 默认值 | 环境变量 | 说明 |
| --- | --- | --- | --- |
| `enabled` | `True` | `POLARIS_AI_A2A_ENABLED` | A2A 注册和发现总开关 |
| `registry.enabled` | `True` | `POLARIS_AI_A2A_REGISTRY_ENABLED` | 创建 A2A registrar |
| `registry.ttl` | `5` | `POLARIS_AI_A2A_TTL` | 自动心跳 TTL，正整数秒 |
| `discovery.enabled` | `True` | `POLARIS_AI_A2A_DISCOVERY_ENABLED` | 创建 A2A resolver |

`service_token` 用于注册、心跳和反注册。它和 connector token 独立，可以为空；服务端是否允许
空 token 由注册中心鉴权策略决定。

### 7.2 A2A 行为

- 每个 transport 注册为一个实例。
- 实例 metadata 写入 `ai-agent-name`、`a2a.agent.card`、`a2a.transport`、`a2a.path`。
- TLS transport 使用 `https` protocol，否则使用 `http`。
- 部分注册失败会回滚本次已成功实例。
- 反注册失败保留在 `registered`，可以再次关闭重试。
- Resolver 每次查询健康实例，按 `host:port` 保持粘性。
- 实例移除、不健康、隔离或卡片失效时切换。
- 查询失败时可复用最近一次成功卡片。
- `PolarisA2AAgent` 在网络失败且尚未收到远端事件时重建客户端。
- 官方 `A2AClientTimeoutError` 按 timeout 指标上报。

## 8. MCP 配置

`PolarisMCPConfig` 位于 `PolarisAgentConfig.mcp`。

| 字段 | 默认值 | 环境变量 | 说明 |
| --- | --- | --- | --- |
| `enabled` | `False` | `POLARIS_AI_MCP_ENABLED` | 启用 MCP resolver |
| `protocol_version` | 空 | `POLARIS_AI_MCP_PROTOCOL_VERSION` | 允许的协议版本，可逗号分隔 |
| `scheme` | 空 | `POLARIS_AI_MCP_SCHEME` | `http/https`；空时使用实例 metadata |
| `timeout` | `30.0` | `POLARIS_AI_MCP_TIMEOUT` | MCP HTTP 超时秒数 |
| `filter_contract` | `True` | `POLARIS_AI_MCP_FILTER_CONTRACT` | 按服务契约禁用 Tool |
| `headers` | 空 | `POLARIS_AI_MCP_HEADERS` | 逗号分隔的 `name=value` |
| `caller_service` | 空 | `POLARIS_AI_MCP_CALLER_SERVICE` | 调用指标中的 caller service |
| `labels` | 空 | `POLARIS_AI_MCP_LABELS` | 调用指标 labels |

MCP 行为：

- 只选择健康且未隔离的实例。
- 支持 `mcp-streamable-http` 和 `mcp-sse`。
- 从 metadata 读取协议版本、endpoint path 和 scheme。
- SSE 使用有状态连接，streamable HTTP 使用无状态配置。
- ClientPool 通过 watch 感知实例变化。
- 池 key 包含 endpoint、transport、实例版本、MCP 协议版本和禁用 Tool 集合。
- 契约或版本变化会原子重建客户端。
- 关闭与手动 refresh 使用同一锁，关闭后不会重新装入客户端。
- MCP Tool 调用按原 Tool 名和 `instance_type="mcp"` 上报。

## 9. AI 日志配置

不传 `ai_log_options` 时，不创建 Polaris AI 文件，模块日志交给应用 Python logging。

```python
from polaris_ai import PolarisAILogOptions

ai_options = PolarisAILogOptions(
    level="info",
    log_dir="./polaris/log/ai",
    max_bytes=50 * 1024 * 1024,
    backup_count=5,
    max_age_days=30,
    capture_agentscope=False,
    warning_throttle_seconds=30,
)
```

| 字段 | 默认值 | 环境变量 | 说明 |
| --- | --- | --- | --- |
| `level` | `info` | `POLARIS_AI_LOG_LEVEL` | `debug/info/warn/warning/error` |
| `log_dir` | `./polaris/log/ai` | `POLARIS_AI_LOG_PATH` | 分类日志根目录 |
| `file_path` | 空 | `POLARIS_AI_LOG_PATH` | 显式基础文件名，与 `log_dir` 互斥 |
| `max_bytes` | 50MB | 无 | 单文件滚动大小 |
| `backup_count` | 5 | 无 | 编号备份数 |
| `max_age_days` | 30 | 无 | 备份保留天数，0 关闭 |
| `capture_agentscope` | `False` | `POLARIS_AI_LOG_CAPTURE_AGENTSCOPE` | 桥接 AgentScope `"as"` logger |
| `warning_throttle_seconds` | 30 | 无 | warning 聚合周期，0 关闭 |

优先级：

```text
PolarisAILogOptions 显式值 > POLARIS_AI_LOG_* > 默认值
```

`log_dir` 和 `file_path` 互斥：

- `log_dir` 模式会在文件名中追加稳定 `clientId`。
- `file_path` 模式不追加 `clientId`，适合由部署系统提供唯一文件路径的场景。
- `POLARIS_AI_LOG_PATH` 指向已有目录、无扩展名路径或以 `/`、`\` 结尾时按 `log_dir` 处理；
  有扩展名时按 `file_path` 处理。

分类：

- `base`：Runtime 生命周期和配置摘要。
- `agentscope`：Agent、Toolkit、中间件和 Skill 快照。
- `skill`：列表、缓存、下载、版本和解压。
- `a2a`：注册、反注册、发现、卡片和重试。
- `mcp`：候选、契约、连接池和关闭。
- `metrics`：A2A/MCP 调用结果上报失败。

默认目录：

```text
./polaris/log/ai/
  base/polaris-ai-base-<clientId>.log
  agentscope/polaris-ai-agentscope-<clientId>.log
  skill/polaris-ai-skill-<clientId>.log
  a2a/polaris-ai-a2a-<clientId>.log
  mcp/polaris-ai-mcp-<clientId>.log
  metrics/polaris-ai-metrics-<clientId>.log
```

每个分类按首次使用创建，默认最多保留一个活动文件、5 个编号备份，并清理 30 天以前备份。

日志级别策略：

- `INFO`：生命周期和状态集合变化。
- `DEBUG`：分页、缓存命中、候选过滤、地址选择和重试细节。
- `WARNING`：可恢复错误，按 key 和 `warning_throttle_seconds` 聚合。
- `ERROR`：初始化失败或无法恢复错误。

Warning 聚合期结束后的下一条日志会附带：

```text
[suppressed N similar warnings]
```

AgentScope `"as"` logger 是进程级全局对象。同一进程同一时刻只允许一个活动 Runtime 启用
`capture_agentscope`，且不会调用 `agentscope.setup_logger()`。

## 10. 环境变量总表

### 连接

| 变量 | 说明 |
| --- | --- |
| `POLARIS_AI_ADDRESS` | 注册中心地址，优先于 `POLARIS_AI_ADDRESSES` |
| `POLARIS_AI_ADDRESSES` | 注册中心地址列表 |
| `POLARIS_AI_NAMESPACE` | 命名空间 |
| `POLARIS_AI_CONNECTOR_TOKEN` | connector token |
| `POLARIS_AI_SERVICE_TOKEN` | service token |
| `POLARIS_SERVER_ADDRESS` / `POLARIS_SERVER_ADDRESSES` | 地址回退 |
| `POLARIS_TOKEN` | connector token 回退 |
| `POLARIS_SERVICE_TOKEN` | service token 回退 |

### Skill

| 变量 | 说明 |
| --- | --- |
| `POLARIS_AI_SKILL_ENABLED` | Skill 总开关 |
| `POLARIS_AI_SKILL_ADDRESS` | SkillAPI 地址 |
| `POLARIS_AI_SKILL_NAMES` | 指定名称列表 |
| `POLARIS_AI_SKILL_VERSION` | 固定版本 |
| `POLARIS_AI_SKILL_LIST_LIMIT` | 分页大小 |
| `POLARIS_AI_SKILL_MAX_SKILLS` | 最大数量 |
| `POLARIS_AI_SKILL_LIST_REFRESH_INTERVAL_SECONDS` | 列表刷新间隔 |
| `POLARIS_AI_MOUNTED_SKILL_ENABLED` | 挂载模式 |
| `POLARIS_AI_MOUNTED_SKILL_SERVICE` | 挂载服务名 |
| `POLARIS_AI_SKILL_ATTACH_TO_AGENT` | 自动接入 Agent |
| `POLARIS_AI_A2A_CARD_NAME` | 挂载服务名回退 |
| `POLARIS_AI_AGENT_NAME` | 挂载服务名回退 |
| `POLARIS_SKILL_SERVER_ADDRESS` | Skill 地址回退 |

### A2A

| 变量 | 说明 |
| --- | --- |
| `POLARIS_AI_A2A_ENABLED` | A2A 总开关 |
| `POLARIS_AI_A2A_REGISTRY_ENABLED` | 注册开关 |
| `POLARIS_AI_A2A_DISCOVERY_ENABLED` | 发现开关 |
| `POLARIS_AI_A2A_TTL` | 心跳 TTL |

### MCP

| 变量 | 说明 |
| --- | --- |
| `POLARIS_AI_MCP_ENABLED` | MCP 开关 |
| `POLARIS_AI_MCP_PROTOCOL_VERSION` | 协议版本 |
| `POLARIS_AI_MCP_SCHEME` | HTTP scheme |
| `POLARIS_AI_MCP_TIMEOUT` | 请求超时 |
| `POLARIS_AI_MCP_FILTER_CONTRACT` | 契约过滤 |
| `POLARIS_AI_MCP_HEADERS` | headers |
| `POLARIS_AI_MCP_CALLER_SERVICE` | caller service |
| `POLARIS_AI_MCP_LABELS` | labels |

### 日志

| 变量 | 说明 |
| --- | --- |
| `POLARIS_AI_LOG_LEVEL` | AI 日志级别 |
| `POLARIS_AI_LOG_PATH` | AI 日志目录或基础文件 |
| `POLARIS_AI_LOG_CAPTURE_AGENTSCOPE` | AgentScope logger 桥接 |
| `POLARIS_LOG_LEVEL` | Core SDK 日志级别 |
| `POLARIS_LOG_PATH` | Core SDK 日志路径 |

## 11. 环境变量示例

```bash
export POLARIS_AI_ADDRESS=127.0.0.1:8091
export POLARIS_AI_NAMESPACE=default
export POLARIS_AI_CONNECTOR_TOKEN=
export POLARIS_AI_SERVICE_TOKEN=

export POLARIS_AI_SKILL_ENABLED=true
export POLARIS_AI_SKILL_NAMES=weather,calculator
export POLARIS_AI_SKILL_ATTACH_TO_AGENT=true

export POLARIS_AI_A2A_ENABLED=true
export POLARIS_AI_A2A_REGISTRY_ENABLED=true
export POLARIS_AI_A2A_DISCOVERY_ENABLED=true
export POLARIS_AI_A2A_TTL=5

export POLARIS_AI_MCP_ENABLED=false

export POLARIS_AI_LOG_LEVEL=info
export POLARIS_AI_LOG_PATH=./polaris/log/ai
export POLARIS_AI_LOG_CAPTURE_AGENTSCOPE=false
```

```python
config = PolarisAgentConfig.from_env(agent_name="weather-agent")
runtime = PolarisAgentRuntime(
    config,
    ai_log_options=PolarisAILogOptions(),
)
```

## 12. 直接使用适配器

不使用 `PolarisAgentRuntime` 时，可以单独创建适配器。

### 共享 Context

`PolarisAgentContext`：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `namespace` | `default` | 默认请求 namespace |
| `address` | `127.0.0.1:8091` | 单个地址或地址列表 |
| `connector_token` | 空 | SDK 接入 token |
| `skill_address` | 空 | SkillAPI 地址；空时从发现地址推导 8094 |
| `log_options` | 无 | Core SDK 日志配置 |
| `sdk_context` | 无 | 借用已有 Context |

自建 Context 会关闭 stat reporter 和 provider lossless；借用 Context 保持原配置。

### Skill

`PolarisSkillLoader` 主要参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `namespace` | `default` | Skill namespace |
| `service_name` | 空 | 挂载服务名 |
| `version` | 空 | 固定版本 |
| `names` | 空 | 指定 Skill |
| `list_limit` | 50 | 分页大小 |
| `max_skills` | 100 | 最大数量 |
| `refresh_interval` | 30.0 | 列表缓存秒数 |
| `timeout` | 0 | Skill 请求超时毫秒 |

### A2A

| 类 | 主要参数 | 说明 |
| --- | --- | --- |
| `PolarisA2ARegistrar` | `namespace`、`service_token`、`ttl` | 创建、心跳、反注册 |
| `PolarisA2AResolver` | `namespace`、`timeout`（毫秒） | 发现和粘性选实例 |
| `PolarisA2AAgent` | `agent_name`、`agent_factory`、`reporter`、`caller_service`、`labels` | 原生 A2A Agent 包装和重试 |
| `PolarisA2AServerRegistration` | `agent_card`、`transports`、`server_ready` | 服务就绪后注册，退出时反注册 |

`A2ATransport`：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `host` | 必填 | 业务实例地址，不使用 SDK bindIP |
| `port` | 必填 | 已监听端口 |
| `transport` | `JSONRPC` | transport 类型 |
| `path` | `/` | A2A endpoint 绝对路径 |
| `support_tls` | `False` | 是否注册为 HTTPS |

`server_ready` 支持 `asyncio.Event`、awaitable 或返回 awaitable 的 callable。

### MCP

`PolarisMCPResolver` 主要参数已经列在 MCP 配置章节。额外的代码参数：

- `client_factory`：自定义 MCP Client 工厂。
- `logger`：MCP 分类日志实例。
- `metrics_logger`：调用上报日志实例。

`PolarisMCPClientPool` 提供：

- `start()`：首次加载并订阅 watch。
- `refresh()`：手动原子刷新。
- `choose_client()`：轮询选择客户端。
- `close()`：停止刷新、解除 watch、关闭全部客户端。

构造池时可以覆盖 resolver 默认值：

```python
pool = PolarisMCPClientPool(
    resolver,
    "search-mcp",
    protocol_version="2025-06-18",
    scheme="https",
    timeout=10,
    headers={"X-Client": "my-agent"},
    filter_contract=True,
)
```

### AgentCard

`PolarisAgentCardTemplate`：

| 字段 | 默认值 |
| --- | --- |
| `description` | 空 |
| `version` | `1.0.0` |
| `protocol_binding` | `JSONRPC` |
| `protocol_version` | `1.0` |
| `input_modes` | `("text/plain",)` |
| `output_modes` | `("text/plain",)` |
| `streaming` | `True` |
| `skills` | 空 |

## 13. 功能边界

当前支持：

- AgentScope Skill 已发布和挂载读取。
- Skill Toolkit、动态刷新和快照降级。
- A2A 注册、心跳、发现、AgentCard、黏性路由和重试。
- MCP 发现、契约过滤、ClientPool watch、客户端重建。
- A2A/MCP 调用结果上报。
- 多 Context 配置、连接、日志和资源隔离。
- AI 分类日志、滚动、保留、文件锁和 warning 聚合。

当前不支持：

- Skill 保存、删除、发布和上传。
- 服务治理规则拉取，包括限流、路由、熔断和无损规则。
- watch 事件用于通用 Skill 刷新 API。
- 自定义日志 formatter 和按分类级别。
- 多 Runtime 同时桥接 AgentScope `"as"` logger。
- LangGraph 集成。

## 14. 安全检查

不要写入日志或提交到仓库：

- connector token
- service token
- MCP Authorization header
- 完整 AgentCard 中的私有业务信息
- Skill ZIP 内容
- 业务请求和响应正文

Skill 和 MCP 日志只记录服务、实例、版本、数量、状态和错误类型，不记录 token 或 headers
明文。
