# AgentScope 分组测试说明

## 脚本作用

四个脚本统一放在 integration 根目录，从任意工作目录使用绝对路径也可执行。
以下命令在仓库根目录执行：

```bash
./integration/verify.sh --only agentscope
./integration/verify_e2e.sh --only agentscope
./integration/verify_e2e.sh --only agentscope/a2a/provider --retain
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

分组选择可以用逗号分隔。A2A provider 和 consumer 选择器都运行完整配对验证，
不会要求手动启动另一个进程。所有场景各自启动子进程，失败后继续其他场景，最后汇总。

## 离线验证

分组验证包含标准与流式 A2A、会话恢复、已发布/挂载/Skill Console、
标准与 Agent Tool MCP、PolarisAgentRuntime、多 Agent Runtime 和 Agent Service。

只替换 Polaris 的 protobuf gRPC 调用边界，SDK Context、插件、自动心跳、
缓存、日志和 AgentScope 都使用真实实现。A2A HTTP 服务使用本机动态端口，
没有外部注册中心依赖，也不需要模型 API 密钥。Skill ZIP 使用有 name 和 description
front matter 的 SKILL.md 以及可读取的 references.txt，不能以空列表作为验证通过条件。
loader 关闭后临时目录必须删除，借用的 Context 在应用显式 destroy 前保持可用。

## 远端验证

```bash
export POLARIS_SERVER_ADDRESS='<host>:8091'
export POLARIS_SKILL_NAME='<published-skill>'
export POLARIS_AGENT_SERVICE='<service-with-mounted-skills>'
export POLARIS_MCP_SERVICE='<existing-mcp-service>'
export POLARIS_E2E_NAMESPACE=polaris-python-ai-integration
./integration/verify_e2e.sh --only agentscope
```

A2A 服务 token 可为空，取决于服务端是否开启鉴权。未设置
`POLARIS_SKILL_NAME` 时，新增 Skill 场景会从目标命名空间读取第一个已发布
Skill；挂载 Skill 仍要求预先挂载的 `POLARIS_AGENT_SERVICE`，MCP 解析 case
需要 `POLARIS_MCP_SERVICE` 指向已有 MCP 服务。每个场景只检查
自己需要的变量，缺失时失败退出，不会悄悄切回离线替身。
Skill 场景只读取和下载，不上传、不发布。
标准及 Skill A2A case 注册实例后发现它，校验默认注册端口 `1`、空的实例 protocol、
`ai-agent-name` / `ai-agent-card` / `ai-a2a-version` metadata，以及
JSONRPC + HTTP+JSON 多 interface 单实例。保持超过两个 TTL 后反注册。
retain 模式使用 JSONRPC 1.0、JSONRPC 0.3 和 HTTP+JSON 1.0 三个接口，
验证后保持实例与 Provider 进程，直到 cleanup。
流式及状态恢复 case 不执行相同的心跳等待或 multi-interface 矩阵。
真实 Skill 验证已有 ZIP、Toolkit 说明、同版本缓存和 loader 关闭后的目录清理，
不在远端运行离线的错误注入与固定版本矩阵。

可选环境变量：

- POLARIS_E2E_NAMESPACE：请求命名空间，默认 polaris-python-ai-integration；default 会被拒绝。
- POLARIS_E2E_SERVICE_TOKEN：优先于 POLARIS_SERVICE_TOKEN。
- POLARIS_TOKEN：SDK connector 接入 token，由 SDK 读取，与服务 token 分开。
- POLARIS_SKILL_SERVER_ADDRESS：覆盖 Skill 地址；设置 --address 时示例默认使用同主机 8094。
- POLARIS_SKILL_VERSION：指定 Skill 下载版本；挂载版本仍优先。
- POLARIS_E2E_CONFIG：真实验证使用的 polaris.yaml 绝对路径，便于配置 TLS 等。
- POLARIS_PYTHON：指定已安装依赖的 Python 解释器。

这些 E2E 辅助变量由 integration 消费，不是额外 SDK YAML 字段。
真实场景同时启用事件 Pushgateway，使用注册中心 host 的 9091 端口。
POLARIS_EVENT_REPORTER_* 配置在示例公共入口应用，事件上报错误可从 event 日志查看；
本验证不以独立事件服务存在作为断言前提。

## 执行产物与解读

每次执行在对应场景目录创建 .logs/verify-时间-编号/ 或
.logs/verify-e2e-时间-编号/，并保留：

- console.log：子进程合并输出和最后的验证 JSON。
- verification.log：验证输出、异常和 traceback。
- result.json：exit_code、timed_out、interrupted 和 action。
- polaris/log/：按 provider、consumer、probe 等组件隔离的 SDK 分类日志。
- polaris/log/ai/：base、agentscope、skill、a2a、mcp、metrics 分类的 AI 扩展日志。
- polaris/backup/：当前运行的实例缓存与 Skill 备份。
- work/：运行工作目录，与源码目录隔离。

只有退出码为 0、未超时且未中断才判定通过。离线默认每场景 180 秒；
真实验证默认 300 秒，可传 --timeout 60 覆盖。先看 result.json，再看
verification.log、console.log 和 SDK 分类日志。所有 Context 都验证独立 clientId
与销毁后的后台线程停止，失败也通过 finally 关闭。

## 进程与组件

`--only agentscope` 与默认全量运行一样，按顺序运行 13 个 case。
`runner.py` 每次只启动一个 `scenarios.py` 验证子进程；Provider、Consumer、
Probe、Uvicorn 与本地 Agent 都在该子进程内。A2A、MCP Agent 和 Agent Service
启动业务监听器，Skill/Runtime 不启动监听器。离线 Stub 也是进程内对象。

Polaris、Skill 服务、Pushgateway 及前置 MCP/挂载服务由外部环境提供，
不会自动启动。验证结束关闭自建监听器、客户端及 SDK Context，不保留业务进程。
唯一例外是 A2A Provider 的 `--retain` 模式：Provider 作为独立进程登记 PID，
验证进程退出后继续心跳，等待 cleanup 停止。

## 注册服务与实例

真实命名空间默认 `polaris-python-ai-integration`，时间戳共 20 位。
标准 A2A、流式 Provider、Console、状态恢复、A2A Skill 共注册 5 个服务、
各 1 个实例：`agentscope-a2a-*`、两次独立的 `agentscope-a2a-streaming-*`、
`agentscope-a2a-state-resume-*`、`agentscope-a2a-skill-*`。
每个 A2A 实例为本机源 IP、port `1`、空 protocol、version `1.0.0`、TTL `1`；
卡片的多 interface 和动态业务端口不产生额外实例。

MCP Agent 另注册 `agentscope-mcp-agent-*` 的 1 个实例，使用本机源 IP 与
动态监听端口、protocol `mcp-streamable-http`。Agent Service 另注册
`agentscope-agent-service-*` 的 1 个实例；当前验证器指定 `127.0.0.1` 与动态
监听端口、protocol `http`。两者 version 均为 `1.0.0`、TTL 均为 `1`。

因此默认全量成功时共 7 个自建服务、每个 1 个实例。纯 Skill/Runtime 不注册，
MCP 解析只读 `POLARIS_MCP_SERVICE`，挂载 Skill 只读 `POLARIS_AGENT_SERVICE`
及已发布资源。离线注册仅存在于各自 Stub。结束时反注册自建实例，但真实服务
对象可能保留，外部资源不删除。

## 访问与验证链路

- A2A：注册/发现 AgentCard → 按卡片 URL 调用 Echo 或流式 Tool → 检查结果
  和反注册；普通 case 的同端口多 interface 不等于实际调用了所有 transport，
  retain case 会实际调用 JSONRPC 1.0、JSONRPC 0.3 和 HTTP+JSON 1.0。
- 状态恢复：同进程两次客户端初始化，通过状态文件延续 `context_id`。
- MCP：解析 case 只查实例和契约，不连 HTTP；Agent case 自建 Server 并实际
  `tools/list`、`tools/call echo_text`。
- Skill：已发布列表或挂载元数据 → 下载 ZIP → loader/Toolkit/本地 Agent 读取
  内容；不调用挂载服务的实例端口。
- Runtime：共享本地组件，检查装配或两个 Agent 的 Skill 回复，不做远程 A2A 调用。
- Agent Service：根据 ready 文件直接 HTTP 调用 `/health` 和 `/chat`，校验
  两个 session；停服后才以 Polaris Probe 确认实例移除。

完整的 case 列表、资源命名和结束语义见 [总说明](../../test.md)。

## 清理

```bash
./integration/cleanup.sh --dry-run
./integration/cleanup.sh --force --keep-logs
./integration/cleanup.sh --force
```

清理仅操作 integration/cases 下有 PID、进程创建时间和命令身份记录的进程以及 .logs/.runtime，
防止 PID 重用误杀。--keep-logs 只停止进程并保留产物；--dry-run 只预览。
retain Provider 必须先通过 dry-run 确认记录可见，再由 `--force` 停止并反注册。
只有显式 --delete-services 才请求 Polaris 删除当前命名空间
agentscope- 前缀服务，可用 POLARIS_CONSOLE_ADDRESS 覆盖管理端点，
默认同主机 8090。不会删除 polaris-python 的 E2E 服务、预先挂载的服务、
发布的 Skill、源码、YAML 或外部缓存目录。
