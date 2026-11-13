# A2A Provider测试说明

## 脚本作用

四个脚本统一放在 integration 根目录，从任意工作目录使用绝对路径也可执行。
以下命令在仓库根目录执行：

```bash
./integration/verify.sh --only agentscope/a2a/provider
./integration/verify_e2e.sh --only agentscope/a2a/provider
./integration/verify_e2e.sh --only agentscope/a2a/provider --retain
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

分组选择可以用逗号分隔。A2A provider 和 consumer 选择器都运行完整配对验证，
不会要求手动启动另一个进程。所有场景各自启动子进程，失败后继续其他场景，最后汇总。
普通验证结束时停止 Provider；只有 `--retain` 在成功后保留独立 Provider 进程。

## 离线验证

此入口运行完整 A2A 配对验证，检查实例 ID、业务 IP、默认注册端口 1、
AgentCard 的三个 metadata 键、自动心跳、反注册和监听器关闭。

只替换 Polaris 的 protobuf gRPC 调用边界，SDK Context、插件、自动心跳、
缓存、日志和 AgentScope 都使用真实实现。A2A HTTP 服务使用本机动态端口，
没有外部注册中心依赖，也不需要模型 API 密钥。本 case 未启用 Skill loader，
不查询或下载 Skill。

## 远端验证

```bash
export POLARIS_SERVER_ADDRESS='<host>:8091'
export POLARIS_SERVICE_TOKEN='<service-token>' # 服务开启鉴权时才需要
export POLARIS_E2E_NAMESPACE=polaris-python-ai-integration
./integration/verify_e2e.sh --only agentscope/a2a/provider
```

本用例只需要真实 Polaris 地址和按需配置的 token，不需要 Skill 或前置业务
Provider。注册后保持超过两个 TTL，再反注册并等待发现结果移除；缺少地址会
失败，不回退到离线替身。

需要让示例进程在验证后继续运行时使用：

```bash
./integration/verify_e2e.sh --only agentscope/a2a/provider --retain
./integration/cleanup.sh --dry-run
./integration/cleanup.sh --force
```

`--retain` 启动 `--multi-protocol` Provider，验证 JSONRPC 1.0、JSONRPC 0.3
和 HTTP+JSON 1.0 三个真实接口。验证成功后 Provider 保持心跳并继续监听；
cleanup 依据 `.runtime/processes` 中的 PID、创建时间和命令记录终止它，
Provider 再走正常反注册和 Context 销毁。

可选环境变量：

- POLARIS_E2E_NAMESPACE：请求命名空间，默认 polaris-python-ai-integration；default 会被拒绝。
- POLARIS_E2E_SERVICE_TOKEN：优先于 POLARIS_SERVICE_TOKEN。
- POLARIS_TOKEN：SDK connector 接入 token，由 SDK 读取，与服务 token 分开。
- POLARIS_SKILL_SERVER_ADDRESS：覆盖 Skill 地址；未设置由 SDK 推导端口 8094。
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
- provider.log：retain 模式独立 Provider 进程的持续输出。
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

`runner.py` 启动一个 `scenarios.py --demo a2a` 子进程，真实验证追加 `--real`。
其中以异步任务运行 `examples/agentscope/a2a/provider/main.py` 的 Uvicorn
Server，并直接调用 `consumer/main.py`；Provider、Consumer 和独立 Probe
有各自 SDK Context，但不另起业务进程。离线 RegistryStub 位于同一进程；
真实 Polaris 与 Pushgateway 由外部提供。

使用 `--retain` 时，标准路径改为由 `scenarios.py` 启动独立的 Provider 子进程，
日志写入本次运行的 `provider.log`，进程身份写入 case 的 `.runtime/processes`。
验证进程退出后 Provider 仍保留；直到 cleanup 发出终止信号。

## 注册服务与实例

真实创建 `agentscope-a2a-<20位微秒时间戳>` 服务，默认命名空间为
`polaris-python-ai-integration`，其下只有本用例注册的 1 个实例：

- host：连接 Polaris 的本机源 IP；离线为 `127.0.0.1`。
- port：注册身份端口 `1`；protocol 为空，version `1.0.0`；retain 模式为
  `2.1.0`，TTL `1`。
- metadata：`ai-agent-name`、`ai-agent-card`、`ai-a2a-version=1.0`。
- AgentCard：普通模式包含同一个动态 HTTP 端口的 JSONRPC `/` 与 HTTP+JSON
  `/rest`；retain 模式包含 JSONRPC 1.0 `/a2a/v1`、JSONRPC 0.3
  `/a2a/legacy` 和 HTTP+JSON 1.0 `/rest` 三个 interface。均不注册第二个实例。

Consumer 和 Probe 不注册服务或实例。离线使用 `offline-echo-agent`，实例只
写入 Stub。结束时反注册唯一实例并关闭 Server；真实服务对象可能保留。

## 访问与验证链路

1. Provider 监听成功后注册；Probe 经 Polaris Discover 找到健康、非隔离实例，
   校验实例 ID、IP、注册端口、version 和三个 metadata 键。
2. Consumer 的 PolarisA2AResolver 发现该服务，从 AgentCard URL 创建 A2AAgent，
   调用实际 HTTP 端口，发送 `Hello Polaris`，断言 `Echo: Hello Polaris`。
   普通模式使用 JSONRPC/SSE；retain 模式分别通过 JSONRPC 1.0、JSONRPC 0.3
   和 HTTP+JSON 1.0 发送真实请求并校验三个 Echo 结果。
3. 离线等待至少一次自动心跳；真实等待 3.2 秒后确认 TTL `1` 的实例仍可发现。
4. 取消 Provider，等待 Probe 发现结果移除实例，检查本机监听器已关闭。
   离线还检查仅 1 次注册/反注册，且反注册后心跳计数停止增长；销毁各 Context。

调用链为 Consumer → Polaris 获取卡片 → 本机 Provider，Polaris 不代理业务请求。
普通实际验证函数为 `integration/scenarios.py::verify_a2a`；retain 模式为
`integration/scenarios.py::verify_retained_a2a`。

## 清理

```bash
./integration/cleanup.sh --dry-run
./integration/cleanup.sh --force --keep-logs
./integration/cleanup.sh --force
```

清理仅操作 integration/cases 下有 PID、进程创建时间和命令身份记录的进程以及 .logs/.runtime，
防止 PID 重用误杀。--keep-logs 只停止进程并保留产物；--dry-run 只预览。
`--retain` 产生的 Provider 只能由 cleanup 停止；`--dry-run` 必须先能看到对应进程记录。
只有显式 --delete-services 才请求 Polaris 删除当前命名空间
agentscope- 前缀服务，可用 POLARIS_CONSOLE_ADDRESS 覆盖管理端点，
默认同主机 8090。不会删除 polaris-python 的 E2E 服务、预先挂载的服务、
发布的 Skill、源码、YAML 或外部缓存目录。
