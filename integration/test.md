# 全部 AgentScope 场景测试说明

## 脚本作用

四个脚本统一放在 integration 根目录，从任意工作目录使用绝对路径也可执行。
以下命令在仓库根目录执行：

```bash
./integration/verify.sh
./integration/verify_e2e.sh
./integration/verify_e2e.sh --only agentscope/a2a/provider --retain
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

分组选择可以用逗号分隔。A2A provider 和 consumer 选择器都运行完整配对验证，
不会要求手动启动另一个进程。所有场景各自启动子进程，失败后继续其他场景，最后汇总。

## 离线验证

覆盖标准/流式 A2A、A2A 状态恢复、MCP Tool 调用、已发布/挂载 Skill、
Skill Console、单 Runtime 多 Agent 和精简 Agent Service。具备自注册能力的 case
检查注册、调用与反注册；心跳等待和端口探测按各子用例执行。A2A 默认注册端口为 1，
多 interface 使用同一个实例，调用端口从 AgentCard 获取。

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
./integration/verify_e2e.sh
```

A2A 服务 token 可为空。未设置 `POLARIS_SKILL_NAME` 时，新增 Skill 场景会
自动读取目标命名空间中的已发布 Skill；挂载 Skill 需预先挂载的
`POLARIS_AGENT_SERVICE`。MCP 解析 case 需要已有的 `POLARIS_MCP_SERVICE`。
每个场景只检查自己需要的变量，缺失时失败退出，
不会悄悄切回离线替身。Skill 场景只读取和下载，不上传、不发布。
标准及 Skill A2A case 注册实例后发现它，校验三个 metadata 键、空 protocol、
注册端口 1 和同端口多 interface，再保持超过两个 TTL 并反注册。
流式及状态恢复 case 的等待和断言范围见各自说明。
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
- provider.log：A2A retain 模式独立 Provider 进程的持续输出。
- verification.log：验证输出、异常和 traceback。
- result.json：exit_code、timed_out、interrupted 和 action。
- polaris/log/：按 provider、consumer、probe 等组件隔离的 SDK 分类日志。
- polaris/backup/：当前运行的实例缓存与 Skill 备份。
- work/：运行工作目录，与源码目录隔离。

只有退出码为 0、未超时且未中断才判定通过。离线默认每场景 180 秒；
真实验证默认 300 秒，可传 --timeout 60 覆盖。先看 result.json，再看
verification.log、console.log 和 SDK 分类日志。所有 Context 都验证独立 clientId
与销毁后的后台线程停止，失败也通过 finally 关闭。

## 进程与组件

入口脚本进入 `integration/runner.py`，默认按顺序运行 13 个 case。每个 case
另起一个 `python integration/scenarios.py --demo <场景>` 子进程，真实验证追加
`--real`；任一时刻只运行一个 case。Provider、Consumer、Probe、Agent、
Uvicorn 和 SDK 后台线程均在该子进程内，不是独立业务进程。
仅 `--retain` A2A Provider 模式会在成功验证后保留独立 Provider 进程，并在
case 的 `.runtime/processes` 登记 PID、创建时间和命令，等待 cleanup 停止。

- A2A：同进程启动 HTTP Provider、Consumer 和独立 SDK Probe；流式 Provider
  用例与 Console Consumer 用例各自重新启动一套组件。
- MCP：解析用例只启动客户端逻辑；Agent 用例在同进程启动 MCP HTTP Server
  和调用它的 Agent。
- Skill / Runtime：运行 loader、Toolkit 或本地 Agent，不启动业务监听器。
- Agent Service：同进程启动 FastAPI/Uvicorn、HTTP 验证客户端和退出探针。

离线 Polaris/Skill RPC 由进程内 `RegistryStub` 替代，没有注册中心子进程。
真实 Polaris、Skill 服务、Pushgateway，以及前置 MCP/挂载 Skill 服务须由外部
环境提供，脚本不会拉起它们。所有 case 结束时关闭自建组件，不保留业务进程。
`--retain` 是唯一例外，必须由 cleanup 显式结束。

## 注册服务与实例

真实验证默认命名空间为 `polaris-python-ai-integration`。新建服务的时间戳为
`YYYYMMDDhhmmssffffff`，共 20 位；默认全部 case 成功时有 7 次新建服务注册：

- 标准 A2A：`agentscope-a2a-<时间戳>`，1 个实例。
- Streaming Provider / Console Consumer：各建一个
  `agentscope-a2a-streaming-<时间戳>` 服务，各 1 个实例。
- 状态恢复：`agentscope-a2a-state-resume-<时间戳>`，1 个实例。
- A2A Skill：`agentscope-a2a-skill-<时间戳>`，1 个实例。
- MCP Agent：`agentscope-mcp-agent-<时间戳>`，1 个实例。
- Agent Service：`agentscope-agent-service-<时间戳>`，1 个实例。

A2A 实例均为本机连接 Polaris 的源 IP、注册端口 `1`、空 protocol、
version `1.0.0`、TTL `1`，三个 metadata 键为 `ai-agent-name`、`ai-agent-card`、
`ai-a2a-version`。一个 AgentCard 对应一个实例，多 interface 不增加实例；
HTTP 动态端口在卡片 URL 中，不能拿注册端口 `1` 发业务请求。
MCP Agent 使用同一源 IP 与实际动态监听端口，protocol 为
`mcp-streamable-http`、version `1.0.0`、TTL `1`。Agent Service 当前验证器
显式传入 `127.0.0.1`，实例为该地址加动态端口，protocol `http`、
version `1.0.0`、TTL `1`，不采用 A2A 的注册端口。

MCP 解析 case 只读 `POLARIS_MCP_SERVICE` 的已有实例；挂载 Skill 只读
`POLARIS_AGENT_SERVICE` 的服务扩展元数据。其他 Skill/Runtime case 不注册服务
或实例，也不上传、发布 Skill。离线对应资源仅存在于每个 case 的独立 Stub，
不会在真实 Polaris 创建；具体固定服务名见各 case 文档。
自建实例结束时反注册，真实服务对象仍可能保留；外部服务、实例和 Skill 不删除。
retain A2A 服务在验证成功后继续保持健康和自动心跳，直到 cleanup 终止 Provider。

## 访问与验证链路

- A2A：Provider 注册并心跳 → Probe/Consumer 从 Polaris 发现实例及 AgentCard
  → Consumer 根据卡片 URL 调用本机 JSON-RPC/SSE → 校验 Echo、流式 Tool
  结果或 Skill 回复 → 取消 Provider 并确认实例消失。多 interface 的 REST
  URL 在普通 case 只检查 metadata；retain 模式实际调用 JSONRPC 1.0、
  JSONRPC 0.3 和 HTTP+JSON 1.0，并保留 Provider 直到 cleanup。
- 状态恢复：两次创建客户端并读写 `work/a2a-state.json`，确认同一个
  `context_id` 延续；当前是同进程两次初始化，不是跨进程重启验证。
- MCP 解析：发现已有实例 → 拼接 `/mcp` URL → 读取契约的禁用 Tool 列表；
  不连接 MCP HTTP。MCP Agent：注册自建 Server → 发现 → MCP 初始化及
  `tools/list` → Agent 实际 `tools/call echo_text` → 校验回复后反注册。
- Skill：查询已发布列表或读取服务挂载元数据 → Skill RPC 下载 ZIP →
  loader/Toolkit 读取说明、缓存并清理临时资源。没有对挂载服务实例的 HTTP 调用。
- Runtime：共享 loader/Toolkit 给本地 Agent，验证适配器装配或 Skill 回复；
  不产生新的 A2A/MCP 业务调用。
- Agent Service：读 ready 文件取得 URL → `GET /health`、两次 `POST /chat`
  → 校验 Skill/Echo 回复及两个 session → 停服后用 Polaris Probe 检查反注册。

事件上报是各 SDK Context 到外部 Pushgateway 的独立支路，不是 Consumer
访问 Provider 的业务链路。各子用例的断言和资源明细见相应 `test.md`。

## 清理

```bash
./integration/cleanup.sh --dry-run
./integration/cleanup.sh --force --keep-logs
./integration/cleanup.sh --force
```

清理仅操作 integration/cases 下有 PID、进程创建时间和命令身份记录的进程以及
.logs/.runtime，
防止 PID 重用误杀。--keep-logs 只停止进程并保留产物；--dry-run 只预览。
retain Provider 必须先通过 dry-run 确认记录可见，再由 `--force` 停止并触发反注册。
只有显式 --delete-services 才请求 Polaris 删除当前命名空间
agentscope- 前缀服务，可用 POLARIS_CONSOLE_ADDRESS 覆盖管理端点，
默认同主机 8090。不会删除 polaris-python 的 E2E 服务、预先挂载的服务、
发布的 Skill、源码、YAML 或外部缓存目录。
