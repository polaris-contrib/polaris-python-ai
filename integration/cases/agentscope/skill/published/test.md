# 已发布 Skill测试说明

## 脚本作用

四个脚本统一放在 integration 根目录，从任意工作目录使用绝对路径也可执行。
以下命令在仓库根目录执行：

```bash
./integration/verify.sh --only agentscope/skill/published
./integration/verify_e2e.sh --only agentscope/skill/published
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

此选择器只运行 Published Skill case，不启动 A2A Provider 或 Consumer。

## 离线验证

默认查询分页列表，按 active 版本下载；再以代码指定版本验证覆盖。注入一次下载失败，检查下次加载重试、成功缓存复用、SKILL.md 和 references.txt 内容。

只替换 Polaris 的 protobuf gRPC 调用边界，SDK Context、缓存、日志和
AgentScope 都使用真实实现，不启动业务 HTTP 服务，也不需要模型 API 密钥。
Skill ZIP 使用有 name 和 description
front matter 的 SKILL.md 以及可读取的 references.txt，不能以空列表作为验证通过条件。
loader 关闭后临时目录必须删除，借用的 Context 在应用显式 destroy 前保持可用。

## 远端验证

```bash
export POLARIS_SERVER_ADDRESS='<host>:8091'
export POLARIS_SKILL_NAME='<published-skill>'
export POLARIS_E2E_NAMESPACE=polaris-python-ai-integration
./integration/verify_e2e.sh --only agentscope/skill/published
```

真实需要可访问的 Polaris/Skill 服务和已发布 Skill。`POLARIS_SKILL_NAME` 可
省略，此时只读查询目标命名空间中已有资源，资源为空则失败，不自动创建。
不需要 `POLARIS_AGENT_SERVICE`，也不注册业务实例。真实验证使用选定资源及
显式或发现到的版本，不注入下载失败，不要求 fixture 固定名称和版本。

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

`runner.py` 启动一个 `scenarios.py --demo published` 子进程，真实模式追加
`--real`。其中先直接运行 `skill/published/main.py`，再新建 Probe Context
和 loader/Toolkit 做断言；没有第二个业务进程，没有 Uvicorn 或 Provider。
离线 RegistryStub 同进程，真实 Polaris/Skill 服务及 Pushgateway 由外部提供。

## 注册服务与实例

不创建或注册任何服务/实例，也不创建、发布或删除 Skill；因此没有本 case
生成的业务 host/port 或实例列表。真实默认命名空间
`polaris-python-ai-integration`，只读指定或自动选出的已发布 Skill。
离线 Stub 提供 `weather`、`lookup` ZIP 与 `published-v1` active 版本，
Probe 用代码版本 `code-v1`；这些是 Skill 资源，不是服务实例。

## 访问与验证链路

1. 示例 loader 查询 `GetSkillList` 并按 active 版本下载 ZIP，Toolkit 读取
   Skill instructions；真实已指定名称时直接按名称/版本下载。
2. Probe 用独立 loader 读取资源并反复 `list_skills`，校验同版本返回同一个
   Skill 对象，名称、description、`SKILL.md` 和非空说明均可读。
3. 离线以 `list_limit=1` 覆盖分页，断言 `weather` / `lookup`、ZIP 格式、
   active `published-v1` 和 Probe `code-v1`；给 `weather` 注入一次下载失败，
   后续加载必须成功，检查 `references.txt`。
4. loader 关闭后确认临时目录删除、借用 Context 尚可用，再由应用销毁
   Context 并检查后台线程停止。

实际链路为 loader/Toolkit → Skill RPC → ZIP 及本地缓存，不存在两个业务
服务间的 HTTP 调用；外部 Skill 保留。源码：`integration/scenarios.py::verify_skills`。

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
