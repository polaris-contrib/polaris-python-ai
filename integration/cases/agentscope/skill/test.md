# Skill 分组测试说明

## 脚本作用

四个脚本统一放在 integration 根目录，从任意工作目录使用绝对路径也可执行。
以下命令在仓库根目录执行：

```bash
./integration/verify.sh --only agentscope/skill
./integration/verify_e2e.sh --only agentscope/skill
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

分组选择可以用逗号分隔。三个 Skill case 各自启动子进程，按顺序执行，
失败后继续其他场景，最后汇总；本分组不运行 A2A Provider/Consumer。

## 离线验证

分别运行已发布、挂载和 Console Agent Skill，验证 Toolkit 说明、ZIP 资源、
版本选择、middleware 快照读取、缓存和临时资源清理。

只替换 Polaris 的 protobuf gRPC 调用边界，SDK Context、缓存、日志和
AgentScope 都使用真实实现。离线没有外部注册中心依赖，也不需要模型 API
密钥。Skill ZIP 使用有 name 和 description
front matter 的 SKILL.md 以及可读取的 references.txt，不能以空列表作为验证通过条件。
loader 关闭后临时目录必须删除，借用的 Context 在应用显式 destroy 前保持可用。

## 远端验证

```bash
export POLARIS_SERVER_ADDRESS='<host>:8091'
export POLARIS_SKILL_NAME='<published-skill>'
export POLARIS_AGENT_SERVICE='<service-with-mounted-skills>'
export POLARIS_E2E_NAMESPACE=polaris-python-ai-integration
./integration/verify_e2e.sh --only agentscope/skill
```

Published 和 Console case 使用 `POLARIS_SKILL_NAME`，未设则查询目标命名空间
已有的已发布 Skill；Mounted case 必须提供有挂载元数据的
`POLARIS_AGENT_SERVICE`。本分组只读取和下载，不上传、不发布、不注册业务实例。
地址或所需资源缺失时失败，不回退 Stub。真实验证检查已有 ZIP、Toolkit 说明、
缓存和关闭后资源清理，不执行离线的失败注入及固定版本矩阵。

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
- polaris/backup/：当前运行的实例缓存与 Skill 备份。
- work/：运行工作目录，与源码目录隔离。

只有退出码为 0、未超时且未中断才判定通过。离线默认每场景 180 秒；
真实验证默认 300 秒，可传 --timeout 60 覆盖。先看 result.json，再看
verification.log、console.log 和 SDK 分类日志。所有 Context 都验证独立 clientId
与销毁后的后台线程停止，失败也通过 finally 关闭。

## 进程与组件

`runner.py` 顺序启动 `scenarios.py --demo published`、`--demo mounted`、
`--demo skill-console` 三个验证子进程，真实模式分别追加 `--real`。
Published/Mounted 在各自进程内运行示例 loader/Toolkit 和额外 Probe loader；
Console 创建一个本地 Agent 与 middleware。它们均不启动业务监听器。
离线 RegistryStub 同进程运行，真实 Polaris/Skill 服务和 Pushgateway 由外部提供。

## 注册服务与实例

三个 case 均不创建服务、实例或 Skill，不发业务注册/心跳。真实默认命名空间
`polaris-python-ai-integration`：Published/Console 只读已有 Skill；Mounted 只读
`POLARIS_AGENT_SERVICE` 的挂载元数据及相应 ZIP，不增加/删除该服务下的实例。
该服务现有实例的数量和 host/port 由外部环境决定，验证不要求或调用其业务端口。

离线 Stub 提供 `weather` / `lookup` 两个 Skill ZIP，并为 `mounted-agent`
模拟 `weather@mounted-v2` 的服务扩展元数据；挂载服务没有实例，仍可验证元数据
解析。Skill ZIP/Toolkit 对象不是注册实例。结束时只清理 loader 临时目录和
Context，外部服务、实例与 Skill 不删除。

## 访问与验证链路

- Published：查询分页列表 → Skill RPC 下载 ZIP → Toolkit 读取说明 → Probe
  验证内容、对象缓存和临时目录清理；离线覆盖 active 版本、代码版本及一次失败重试。
- Mounted：Consumer Discover `POLARIS_AGENT_SERVICE` → 从服务级扩展元数据
  读取当前命名空间挂载项 → 按挂载版本下载 ZIP → Toolkit 检查名称与内容。
  不调用挂载服务实例的 HTTP 端口，不列举无关已发布 Skill。
- Console：读取选定 Skill → 本地 Agent 依次处理 `/skill-list`、`/skill <name>`
  → 断言名称和说明正文；非交互运行，无 Agent 间网络调用或模型 API 请求。

三个 case 都与 Polaris/Skill RPC 通信（离线替换 RPC 边界），不互相访问。
各步骤及版本范围见 [Published](published/test.md)、[Mounted](mounted/test.md)
和 [Console Agent](console_agent/test.md)。

## 清理

```bash
./integration/cleanup.sh --dry-run
./integration/cleanup.sh --force --keep-logs
./integration/cleanup.sh --force
```

清理仅操作 integration/cases 下有 PID、进程创建时间和命令身份记录的进程以及 .logs/.runtime，
防止 PID 重用误杀。--keep-logs 只停止进程并保留产物；--dry-run 只预览。
只有显式 --delete-services 才请求 Polaris 删除当前命名空间
agentscope- 前缀服务，可用 POLARIS_CONSOLE_ADDRESS 覆盖管理端点，
默认同主机 8090。不会删除 polaris-python 的 E2E 服务、预先挂载的服务、
发布的 Skill、源码、YAML 或外部缓存目录。
