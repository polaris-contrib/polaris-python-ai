# A2A 完整链路测试说明

## 脚本作用

四个脚本统一放在 integration 根目录，从任意工作目录使用绝对路径也可执行。
以下命令在仓库根目录执行：

```bash
./integration/verify.sh --only agentscope/a2a
./integration/verify_e2e.sh --only agentscope/a2a
./integration/verify_e2e.sh --only agentscope/a2a/provider --retain
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

分组选择可以用逗号分隔。A2A provider 和 consumer 选择器都运行完整配对验证，
不会要求手动启动另一个进程。所有场景各自启动子进程，失败后继续其他场景，最后汇总。

## 离线验证

启动真实本机 JSON-RPC/SSE 服务；覆盖标准 Echo、流式 Tool Calling、
Console Consumer 非交互路径和 `A2AAgentState` 同进程重新初始化恢复。Provider 注册
TTL 1 秒、默认注册端口 1 的实例；真实调用端口保留在 AgentCard 中。
Consumer 通过原生 A2AAgent 调用。退出后检查实例反注册、端口关闭与
Context 后台线程停止。

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
export POLARIS_E2E_NAMESPACE=polaris-python-ai-integration
./integration/verify_e2e.sh --only agentscope/a2a
```

A2A 服务 token 可为空。未设置已发布 Skill 的 `POLARIS_SKILL_NAME` 时，
新增 Skill 场景会自动选择目标命名空间中的第一个已发布 Skill；
选择挂载来源时需 `POLARIS_AGENT_SERVICE`；未配置它时 Skill case 使用已发布
来源。每个场景只检查自己需要的
变量，缺失时失败退出，不会悄悄切回离线替身。Skill 场景只读取和下载，
不上传、不发布。
标准及 Skill A2A case 注册实例后发现它，保持超过两个 TTL，再反注册并等待
发现结果移除；流式和状态恢复 case 不执行同样的显式心跳等待。
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
- polaris/backup/：当前运行的实例缓存与 Skill 备份。
- work/：运行工作目录，与源码目录隔离。

只有退出码为 0、未超时且未中断才判定通过。离线默认每场景 180 秒；
真实验证默认 300 秒，可传 --timeout 60 覆盖。先看 result.json，再看
verification.log、console.log 和 SDK 分类日志。所有 Context 都验证独立 clientId
与销毁后的后台线程停止，失败也通过 finally 关闭。
使用 `--retain` 时 Provider 失败会立即终止；成功则保留到 cleanup 显式清理。

## 进程与组件

本页命令从根入口选择 5 个 case：标准 A2A、Streaming Provider、Console
Consumer、State Resume、A2A Skill。它们按顺序各启动一个 `scenarios.py`
子进程，Provider、Uvicorn、Consumer 与独立 SDK Probe 均在同一子进程中。
`provider` / `consumer` 选择器是标准配对验证的别名，单独选择仍会运行双方，
但不在默认分组中增加两次运行。

离线使用进程内 RegistryStub；真实 Polaris、Skill 服务和 Pushgateway 不由
case 启动。状态恢复两次创建客户端，不启动第二个 OS 进程。结束时取消 Provider
任务、关闭监听器和 SDK Context，不保留业务进程。唯一例外是
`--only agentscope/a2a/provider --retain`：Provider 作为独立进程登记到
`.runtime/processes`，验证进程退出后继续运行，由 cleanup 停止。

## 注册服务与实例

真实命名空间默认 `polaris-python-ai-integration`。分组新建以下 5 个服务，
每个服务 1 个 A2A 实例，`<时间戳>` 为 20 位微秒时间戳：

- 标准：`agentscope-a2a-<时间戳>`。
- Streaming / Console：各自的 `agentscope-a2a-streaming-<时间戳>`。
- State Resume：`agentscope-a2a-state-resume-<时间戳>`。
- Skill：`agentscope-a2a-skill-<时间戳>`。

实例为连接 Polaris 的本机源 IP、port `1`、空 protocol、version `1.0.0`、
TTL `1`，metadata 保存 `ai-agent-name` / `ai-agent-card` / `ai-a2a-version=1.0`。
标准及 Skill case 的卡片包含同动态端口上的 JSONRPC `/` 和 HTTP+JSON `/rest`，
仍只注册一个实例。流式及状态恢复使用 JSONRPC interface。
retain 模式使用 version `2.1.0`，卡片包含 JSONRPC 1.0 `/a2a/v1`、
JSONRPC 0.3 `/a2a/legacy` 和 HTTP+JSON 1.0 `/rest` 三个 interface，
仍只注册一个实例。

离线标准和 Skill case 使用 `offline-echo-agent`；Skill case 先后做 published、
mounted 两轮，每轮只有 1 个实例，前一轮先反注册。其他 case 使用上述带时间戳
名字，但均只写本地 Stub。真实 Skill case 读取已有资源，不创建挂载服务或 Skill。
所有自建实例反注册后，真实服务对象仍可能保留。

## 访问与验证链路

Provider 监听就绪后注册 → Probe 发现健康实例 → Consumer 读取卡片 URL →
调用本机 A2A 服务 → 断言结果 → 取消 Provider → Probe 等待实例移除。
Consumer、Probe 只消费，不另注册 caller 服务或实例。

- 标准：发送 `Hello Polaris`，断言 `Echo: Hello Polaris`；校验卡片、注册端口
  与业务端口分离。真实等待 3.2 秒确认 TTL `1` 的实例仍在，离线检查心跳计数。
- Streaming / Console：发送天气及算术问题，收集流式文本，断言 Shanghai/Sunny
  和 `42`；没有 stdin 输入，不覆盖交互 `launch_console`。
- State Resume：两次调用共用 `work/a2a-state.json`，断言 `context_id` 不变及
  两轮回复；不验证跨进程重启。
- Skill：Provider 读取已发布或挂载 Skill，Consumer 经 A2A 发送 `/skill-list`
  和 `/skill <name>`，精确验证名称和说明正文；Skill 下载走独立 Skill RPC。

标准多 interface 用例只调用 JSONRPC；retain 模式会依次调用 JSONRPC 1.0、
JSONRPC 0.3 和 HTTP+JSON 1.0 三个真实 endpoint。各 case 的细节见相邻子目录
`test.md`，实际函数在 `integration/scenarios.py`。

## 清理

```bash
./integration/cleanup.sh --dry-run
./integration/cleanup.sh --force --keep-logs
./integration/cleanup.sh --force
```

清理仅操作 integration/cases 下有 PID、进程创建时间和命令身份记录的进程以及
.logs/.runtime，
防止 PID 重用误杀。--keep-logs 只停止进程并保留产物；--dry-run 只预览。
retain Provider 必须先通过 dry-run 确认记录可见，再由 `--force` 停止。
只有显式 --delete-services 才请求 Polaris 删除当前命名空间
agentscope- 前缀服务，可用 POLARIS_CONSOLE_ADDRESS 覆盖管理端点，
默认同主机 8090。不会删除 polaris-python 的 E2E 服务、预先挂载的服务、
发布的 Skill、源码、YAML 或外部缓存目录。
