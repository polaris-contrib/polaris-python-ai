# 挂载 Skill测试说明

## 脚本作用

四个脚本统一放在 integration 根目录，从任意工作目录使用绝对路径也可执行。
以下命令在仓库根目录执行：

```bash
./integration/verify.sh --only agentscope/skill/mounted
./integration/verify_e2e.sh --only agentscope/skill/mounted
./integration/logs.sh --latest --tail 50
./integration/cleanup.sh --dry-run
```

此选择器只运行 Mounted Skill case，不启动 A2A Provider 或 Consumer。

## 离线验证

通过真实 SDK 发现服务快照中的扩展元数据；只加载当前命名空间，挂载 mounted-v2 覆盖代码版本，且不得调用已发布列表接口。

只替换 Polaris 的 protobuf gRPC 调用边界，SDK Context、缓存、日志和
AgentScope 都使用真实实现，不启动业务 HTTP 服务，也不需要模型 API 密钥。
Skill ZIP 使用有 name 和 description
front matter 的 SKILL.md 以及可读取的 references.txt，不能以空列表作为验证通过条件。
loader 关闭后临时目录必须删除，借用的 Context 在应用显式 destroy 前保持可用。

## 远端验证

```bash
export POLARIS_SERVER_ADDRESS='<host>:8091'
export POLARIS_AGENT_SERVICE='<service-with-mounted-skills>'
export POLARIS_E2E_NAMESPACE=polaris-python-ai-integration
./integration/verify_e2e.sh --only agentscope/skill/mounted
```

真实需 `POLARIS_AGENT_SERVICE` 指向目标命名空间中有 Skill 挂载元数据的
服务，并能从 Skill 服务下载对应 ZIP。不需要 `POLARIS_SKILL_NAME` 或 A2A
Provider。所需地址或挂载服务缺失时失败，不回退 Stub；只读验证，不增加、
修改或删除远端挂载项及 Skill。

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

`runner.py` 启动一个 `scenarios.py --demo mounted` 子进程，真实模式追加
`--real`。其中直接运行 `skill/mounted/main.py`，再创建独立 Probe loader
和 Toolkit 做内容/缓存断言，不拉起被挂载服务的业务进程或 HTTP 监听器。
离线 RegistryStub 同进程，真实 Polaris/Skill 服务及 Pushgateway 外部提供。

## 注册服务与实例

本 case 不注册任何服务/实例。真实只读默认命名空间
`polaris-python-ai-integration` 下的 `POLARIS_AGENT_SERVICE`，其现有实例
数量、host/port、version 和 TTL 全由外部环境决定，验证不会新增或反注册它们。
挂载项在服务级 `extended_metadata`，不是业务实例 metadata，也不是新实例。

离线 Stub 提供 `mounted-agent` 的服务快照，实例列表为空，但扩展元数据挂载
当前命名空间 `weather@mounted-v2` 和其他命名空间 `lookup@v1`。
两者 ZIP 均为 Stub 资源，不在真实 Polaris 创建。结束只清理临时文件/Context，
已有服务、实例、挂载关系和 Skill 保留。

## 访问与验证链路

Consumer `GetAllInstances` → Discover 返回服务扩展元数据 → loader 过滤当前
命名空间挂载项 → 用挂载版本通过 Skill RPC 下载 ZIP → Toolkit 读取说明。
不会按服务实例的 host/port 发 HTTP 请求，也不会查询全量已发布列表。

离线断言只加载 `weather`、全部下载版本为 `mounted-v2`（优先于代码
`code-v1`）、不调用 `GetSkillList`，且 `SKILL.md` / `references.txt` 可读。
真实验证对应已有资源的非空内容和同版本缓存，不固定要求 `weather` 或
`mounted-v2`。关闭 loader 后校验临时目录删除、借用 Context 未被销毁，
再显式销毁 Context 并检查线程退出。

源码：`integration/scenarios.py::verify_skills`。

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
