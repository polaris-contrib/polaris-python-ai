# 全部 AgentScope 场景测试说明

## 脚本作用

四个脚本统一放在 examples 根目录，从任意工作目录使用绝对路径也可执行。
以下命令在仓库根目录执行：

```bash
./examples/verify.sh
./examples/verify_e2e.sh
./examples/logs.sh --latest --tail 50
./examples/cleanup.sh --dry-run
```

分组选择可以用逗号分隔。A2A provider 和 consumer 选择器都运行完整配对验证，
不会要求手动启动另一个进程。所有场景各自启动子进程，失败后继续其他场景，最后汇总。

## 离线验证

A2A 注册、心跳、发现、调用、退出清理；已发布和挂载 Skill 的加载。

只替换 Polaris 的 protobuf gRPC 调用边界，SDK Context、插件、自动心跳、
缓存、日志和 AgentScope 都使用真实实现。A2A HTTP 服务使用本机动态端口，
没有外部注册中心依赖，也不需要模型 API 密钥。Skill ZIP 使用有 name 和 description
front matter 的 SKILL.md 以及可读取的 references.txt，不能以空列表作为验证通过条件。
loader 关闭后临时目录必须删除，借用的 Context 在应用显式 destroy 前保持可用。

## 远端验证

```bash
export POLARIS_SERVER_ADDRESS=<host>:8091
export POLARIS_SERVICE_TOKEN=<service-token>
export POLARIS_SKILL_NAME=<published-skill>
export POLARIS_AGENT_SERVICE=<service-with-mounted-skills>
./examples/verify_e2e.sh
```

A2A 需服务 token；已发布 Skill 需预先发布的 POLARIS_SKILL_NAME；
挂载 Skill 需预先挂载的 POLARIS_AGENT_SERVICE。每个场景只检查自己需要的变量，
缺失时失败退出，不会悄悄切回离线替身。Skill 场景只读取和下载，不上传、不发布。
真实 A2A 注册实例后发现它，保持超过两个 TTL，再反注册并等待发现结果移除。
真实 Skill 验证已有 ZIP、Toolkit 说明、同版本缓存和 loader 关闭后的目录清理，
不在远端运行离线的错误注入与固定版本矩阵。

可选环境变量：

- POLARIS_E2E_NAMESPACE：请求命名空间，默认 python-integration。
- POLARIS_E2E_SERVICE_TOKEN：优先于 POLARIS_SERVICE_TOKEN。
- POLARIS_TOKEN：SDK connector 接入 token，由 SDK 读取，与服务 token 分开。
- POLARIS_SKILL_SERVER_ADDRESS：覆盖 Skill 地址；未设置由 SDK 推导端口 8094。
- POLARIS_SKILL_VERSION：指定 Skill 下载版本；挂载版本仍优先。
- POLARIS_E2E_CONFIG：真实验证使用的 polaris.yaml 绝对路径，便于配置 TLS 等。
- POLARIS_PYTHON：指定已安装依赖的 Python 解释器。

这些 E2E 辅助变量由示例消费，不是额外 SDK YAML 字段。
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

## 注册服务与实例

离线实例只存在于替身内，不访问外部 Polaris。真实 A2A 服务名以
polaris-python-ai-e2e- 开头，每次含时间和随机标识，默认命名空间为
python-integration；注册 host 为连接 Polaris 的本机源 IP，端口动态分配，
不同验证不会争用固定端口。实例退出前反注册，服务对象可留在服务端。
Skill 测试使用应用预先准备的服务与资源，不创建或删除它们。

## 清理

```bash
./examples/cleanup.sh --dry-run
./examples/cleanup.sh --force --keep-logs
./examples/cleanup.sh --force
```

清理仅操作 examples 下有 PID、进程创建时间和命令身份记录的进程以及 .logs/.runtime，
防止 PID 重用误杀。--keep-logs 只停止进程并保留产物；--dry-run 只预览。
只有显式 --delete-services 才请求 Polaris 删除当前命名空间
polaris-python-ai-e2e- 前缀服务，可用 POLARIS_CONSOLE_ADDRESS 覆盖管理端点，
默认同主机 8090。不会删除 polaris-python 的 E2E 服务、预先挂载的服务、
发布的 Skill、源码、YAML 或外部缓存目录。
