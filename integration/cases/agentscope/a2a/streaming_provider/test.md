# Streaming A2A Provider 测试

```bash
./integration/verify.sh --only agentscope/a2a/streaming_provider
./integration/verify_e2e.sh --only agentscope/a2a/streaming_provider
```

## 进程与组件

`runner.py` 启动一个 `scenarios.py --demo streaming-provider` 子进程，真实模式
追加 `--real`。它在同进程启动 `streaming_provider/main.py` 的 Uvicorn 任务、
执行 `console_consumer/main.py` 并创建独立 Probe。Provider 内的 DemoChatModel、
weather/calculate/time Tool 均为本地实现，不需要外部模型或工具服务。
离线 RegistryStub 不另起进程；真实 Polaris 与 Pushgateway 由外部提供。

## 注册服务与实例

离线和真实模式都使用 `agentscope-a2a-streaming-<20位微秒时间戳>`；离线只写
Stub，真实写入默认命名空间 `polaris-python-ai-integration`。
该服务只注册 1 个实例：host 为真实连接源 IP（离线 `127.0.0.1`），port `1`、
空 protocol、version `1.0.0`、TTL `1`；metadata 为 `ai-agent-name`、
`ai-agent-card`、`ai-a2a-version=1.0`。卡片 JSONRPC URL 指向本机动态业务端口。
Console Consumer 和 Probe 不注册，Tool 与 A2A context 也不产生新实例。

## 访问与验证链路

Provider 监听并注册 → Probe 发现健康非隔离实例并校验卡片 → Console Consumer
根据卡片 URL 发 JSONRPC/SSE → Provider 的 Agent 本地调用 Tool 并流式返回。
两条消息分别为 `weather in Shanghai` 与 `12 + 30`，验证拼接后的回复包含
`Sunny` / `Shanghai` 和 `42`。time Tool 已装配，但本用例不调用它。

消费端传入 `--message`，不运行交互 `launch_console`。最后取消 Provider，
等待 Probe 确认实例移除，关闭 Server/Context；真实服务对象可能保留。
该函数不做跨 context 隔离矩阵，也不独立等待心跳阈值；主断言是流式回复、
注册/发现/反注册及后台线程退出。产物保留 `console.log`、`verification.log`、
`result.json` 和 `polaris/log/ai/a2a/`。

源码：`integration/scenarios.py::verify_streaming_provider`。
