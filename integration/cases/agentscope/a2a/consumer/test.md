# A2A Consumer测试说明

## 脚本作用

四个脚本统一放在 integration 根目录，从任意工作目录使用绝对路径也可执行。
以下命令在仓库根目录执行：

```bash
./integration/verify.sh --only agentscope/a2a/consumer
./integration/verify_e2e.sh --only agentscope/a2a/consumer
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

分组选择可以用逗号分隔。A2A provider 和 consumer 选择器都运行完整配对验证，
不会要求手动启动另一个进程。所有场景各自启动子进程，失败后继续其他场景，最后汇总。

## 离线验证

此入口启动配套 Provider，发现 AgentCard 并执行真实 JSON-RPC/SSE 调用，精确断言 Echo: Hello Polaris，随后关闭 resolver 和借用的 Context。

只替换 Polaris 的 protobuf gRPC 调用边界，SDK Context、插件、自动心跳、
缓存、日志和 AgentScope 都使用真实实现。A2A HTTP 服务使用本机动态端口，
没有外部注册中心依赖，也不需要模型 API 密钥。本 case 未启用 Skill loader，
不查询或下载 Skill。

## 远端验证

```bash
export POLARIS_SERVER_ADDRESS='<host>:8091'
export POLARIS_SERVICE_TOKEN='<service-token>' # 服务开启鉴权时才需要
export POLARIS_E2E_NAMESPACE=polaris-python-ai-integration
./integration/verify_e2e.sh --only agentscope/a2a/consumer
```

本用例会自行启动配套 Provider，不需要前置 Skill 或另一个业务进程。
服务 token 在服务开启鉴权时才需要；真实地址缺失会失败，不回退到 Stub。
注册实例后保持超过两个 TTL，再反注册并等待发现结果移除。

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

本选择器和 Provider 选择器都进入 `verify_a2a`。`runner.py` 只启动一个
`scenarios.py --demo a2a` 子进程，在其中启动 Provider/Uvicorn 异步任务并执行
Consumer 和独立 Probe；三者 Context 分离，但不分别启动 OS 进程。
离线 Stub 同进程运行，真实 Polaris 和 Pushgateway 由外部提供。

## 注册服务与实例

真实新建 `agentscope-a2a-<20位微秒时间戳>` 服务，默认命名空间
`polaris-python-ai-integration`，Provider 只注册 1 个实例：本机源 IP、port `1`、
空 protocol、version `1.0.0`、TTL `1`。metadata 为 `ai-agent-name`、
`ai-agent-card`、`ai-a2a-version=1.0`。卡片包含同一动态业务端口上的
JSONRPC `/` 和 HTTP+JSON `/rest`，不是两个实例。

离线服务为 `offline-echo-agent`，只存在于 Stub。Consumer 和 Probe 只读，
不创建 caller 服务或实例。退出时反注册 Provider；真实服务对象可能保留。

## 访问与验证链路

1. 等待 Provider 监听并注册，Probe 经 Discover 校验实例 ID、健康状态、IP、
   version 与完整卡片 metadata。
2. Consumer 经 PolarisA2AResolver 发现卡片，按卡片 URL 调用 Provider 的
   JSONRPC/SSE，发送 `Hello Polaris` 并精确断言 `Echo: Hello Polaris`。
   不使用 `instance.host:1` 发业务请求，不实际调用 `/rest`。
3. 离线确认自动心跳出现；真实等待 3.2 秒确认 TTL `1` 的实例仍可发现。
4. 关闭 Consumer/resolver，取消 Provider；Probe 等待实例消失，检查监听器关闭。
   离线还确认仅 1 次注册/反注册及随后心跳停止，最后销毁全部 Context。

Consumer → Polaris 获取地址与卡片 → Provider HTTP 是实际调用链；没有
Provider → Consumer 的反向业务调用。详情也见 [Provider 用例](../provider/test.md)。

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
