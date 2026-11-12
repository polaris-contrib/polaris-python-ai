# A2A Skill 测试说明

离线：

```bash
./integration/verify.sh --only agentscope/a2a/skill
```

真实注册中心：

```bash
./integration/verify_e2e.sh --only agentscope/a2a/skill
```

## 进程与组件

`runner.py` 启动一个 `scenarios.py --demo skill-a2a` 子进程，真实模式追加
`--real`。Provider/Uvicorn、Skill loader、Consumer 和独立 Probe 都在该
进程内。离线依次运行 published、mounted 两轮，前一轮关闭后才启动下一轮；
不是两个 Provider 同时运行。真实只运行一轮：有 `POLARIS_AGENT_SERVICE` 则
读取该服务的挂载 Skill，否则读取已发布 Skill。外部 Polaris/Skill 服务/
Pushgateway 不由脚本拉起，离线使用同进程 Stub。

## 注册服务与实例

真实创建 `agentscope-a2a-skill-<20位微秒时间戳>`，默认命名空间
`polaris-python-ai-integration`，只有 1 个 A2A 实例：本机源 IP、port `1`、
空 protocol、version `1.0.0`、TTL `1`。metadata 为 `ai-agent-name`、
`ai-agent-card`、`ai-a2a-version=1.0`；卡片同一动态端口包含 JSONRPC `/`
与 HTTP+JSON `/rest`，并声明加载到的 Skill，不增加实例。

离线两轮均用 `offline-echo-agent`，每轮注册/反注册 1 个实例，累计 2 次，
同一时刻只有 1 个。published 从 Stub 读取 `weather`；mounted 为同名服务
模拟挂载 `weather@mounted-v2`，不另注册挂载服务的实例。
真实只读取已有 Skill 或挂载服务，不创建、发布或删除它们；Consumer/Probe
不注册。结束反注册自建实例，服务对象可能保留。

## 访问与验证链路

1. Provider loader 经 Skill RPC 查询/下载已发布 Skill，或经 Discover 读取
   `POLARIS_AGENT_SERVICE` 的挂载元数据再下载 ZIP；加载说明后监听并注册卡片。
2. Consumer 经 Polaris 发现本次 A2A 服务，按卡片的 JSONRPC URL 发送
   `/skill-list` 和 `/skill <name>`；Provider 的本地 Agent 读取 Skill 内容并回复。
   不直接请求挂载服务的业务实例端口，HTTP+JSON interface 不额外调用。
3. 断言第一条回复等于 Skill 名称，第二条以 `<name>\n\n` 开头；验证自动
   心跳、实例反注册、标准 A2A 监听器关闭和 Context 后台线程退出。

真实需 `POLARIS_SERVER_ADDRESS`；Skill 名称可由 `POLARIS_SKILL_NAME` 指定，
未设则自动查询已发布或挂载列表。服务 token 仅在开启鉴权时需要。
产物位于本 case 的 `.logs/<run>/`，包含控制台、验证结果及 AI a2a/skill/agentscope 日志。
源码：`integration/scenarios.py::verify_skill_a2a`。
