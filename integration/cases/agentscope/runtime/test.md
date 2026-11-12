# PolarisAgentRuntime 测试说明

离线验证使用真实 Core SDK Context、AgentScope、Skill loader 和 Runtime，
只替换 Polaris gRPC 边界。

```bash
./integration/verify.sh --only agentscope/runtime
./integration/verify.sh --only agentscope/runtime/multi_agent
```

验证内容：

- `PolarisAgentConfig` 与借用 `SDKContext`。
- Skill、A2A 适配器装配，并确认默认未装配 MCP。
- ai_log_options 生成 `polaris/log/ai/base/`、`skill/` 和 `a2a/` 分类日志。
- Runtime 借用 Context 的所有权标记，以及最终 Context 后台线程退出。
- 一个 Runtime 创建两个 Agent，共享 Toolkit/snapshot，并分别返回 Skill 名称与说明。

每次运行保留 `console.log`、`verification.log` 和 `result.json`，结果 JSON 中包含
AI 分类日志相对路径。

真实注册中心：

```bash
export POLARIS_SERVER_ADDRESS='<host>:8091'
./integration/verify_e2e.sh --only agentscope/runtime
```

真实 Skill 名称未显式设置时，验证器会从目标命名空间自动选择第一个
已发布 Skill。

## 进程与组件

从根入口 `--only agentscope/runtime` 顺序运行 Runtime 装配和 Multi-Agent
两个 case，各启动一个 `scenarios.py` 子进程，分别为 `--demo runtime`、
`--demo runtime-multi`。每个 case 内的 Runtime、loader、Toolkit 和 Agent
均为本地对象，不起 Uvicorn、A2A Provider 或 MCP Server。
离线 RegistryStub 同进程，真实 Polaris/Skill 服务和 Pushgateway 外部提供。

## 注册服务与实例

两个 case 均不创建或注册任何 Polaris 服务/实例，不产生心跳注册任务。
装配 case 创建 A2A resolver/registrar 对象，但不调用注册 API、不调用远程 A2A；
MCP 适配器默认关闭。Multi-Agent case 关闭 A2A，创建的 `skill-reader` 和
`skill-viewer` 是本地 Agent 名称，不是注册服务或实例。

离线读取 Stub 的 `weather` ZIP。真实读取 `POLARIS_SKILL_NAME` 或自动选取
目标命名空间内已有的已发布 Skill，不创建、发布或删除资源。默认命名空间为
`polaris-python-ai-integration`，因此没有需列举的业务 host/port。

## 访问与验证链路

- 装配：配置 Runtime 并借用 SDKContext → 经 Skill RPC 下载指定 Skill →
  检查名称、A2A resolver/registrar 已装配、MCP resolver 未装配及 Context 非自有。
  不发起业务 HTTP 或 Agent reply。
- Multi-Agent：同一个 loader 下载 Skill → 共享 Toolkit 给两个本地 Agent →
  分别处理 `/skill-list` 与 `/skill <name>` → 检查两名 Agent、共享 Toolkit、
  名称列表和说明正文。没有 Agent 间网络调用。

每个 case 关闭 Runtime 后再显式销毁借用的 Context，最终检查 Context 线程
停止与 AI 日志。当前集成断言不包含会话隔离、日志锁竞争或 logger 关闭后的
重开探针；这些不应由本页默认通过结果推断。详情见
[Multi-Agent 用例](multi_agent/test.md)。
