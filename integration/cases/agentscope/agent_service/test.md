# Agent Service 测试

```bash
./integration/verify.sh --only agentscope/agent_service
./integration/verify_e2e.sh --only agentscope/agent_service
```

## 进程与组件

`runner.py` 启动一个 `scenarios.py --demo agent-service` 子进程，真实追加
`--real`。子进程以异步任务运行 `agent_service/main.py` 的 FastAPI/Uvicorn、
Skill loader 和按 session 创建的本地 Agent；验证器的 HTTP 请求在同进程
线程中执行，停服后另建 SDK Probe。它们不是独立 Provider/Consumer 进程。
离线 Stub 同进程，真实 Polaris、Skill 服务、Pushgateway 外部提供。

## 注册服务与实例

新建 `agentscope-agent-service-<20位微秒时间戳>`，真实默认命名空间
`polaris-python-ai-integration`，其下只有 1 个实例。当前验证器显式传入
`host=127.0.0.1`，即使真实 E2E 也如此；port 为动态 HTTP 监听端口，protocol
`http`、version `1.0.0`、TTL `1`。metadata 为 `framework=agentscope`、
`agent-service=true`，没有 A2A AgentCard 注册端口。

两个 session 只在应用内创建 Agent，不增加实例或 caller 服务。离线注册
只在 Stub；真实只读取指定或自动选择的已发布 Skill，不创建/发布 Skill。
应用退出前反注册唯一实例，但真实服务对象可能保留。

## 访问与验证链路

1. Server 监听并注册后写 `work/agent-service-ready.json`；验证器直接从此文件
   取得 `endpoint`，不是先经 Consumer Discover 选实例再调用。
2. 直接请求 `GET /health`，断言 `status=ok`、Skill loader 已启用。
3. `POST /chat` 用 `session_id=first` 发送 `/skill-list`，本地 Agent 经 Skill RPC
   下载/读取说明，断言回复含 Skill 名称。第二次用 `session_id=second` 发送
   `plain service message`，断言 `Echo: plain service message`。
4. 再请求 `/health`，断言 `sessions=2`；取消 Server，关闭 loader 和监听器，
   用 Polaris Probe 等待该实例消失。离线还检查 Stub 无残留实例。

这是 HTTP 客户端 → 本机 Agent Service 与 Agent → Skill RPC 两条链路。
不覆盖远端 Consumer 的跨主机访问，也没有独立端口关闭探针；最终检查 Context
后台线程停止。保留控制台、验证结果、ready 文件及 Core/AI 分类日志。

源码：`integration/scenarios.py::verify_agent_service`。
