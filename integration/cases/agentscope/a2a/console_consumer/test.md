# A2A Console Consumer 测试

```bash
./integration/verify.sh --only agentscope/a2a/console_consumer
./integration/verify_e2e.sh --only agentscope/a2a/console_consumer
```

## 进程与组件

本选择器同 Streaming Provider 一样运行 `verify_streaming_provider`，只启动
一个 `scenarios.py --demo streaming-provider` 子进程。在其中启动配套 Uvicorn
Provider 任务，执行 Console Consumer 并创建独立 SDK Probe，不启动独立的
Provider/Consumer OS 进程。离线 Stub 也是进程内对象；真实 Polaris 和
Pushgateway 须由外部环境提供。

## 注册服务与实例

本次独立创建 `agentscope-a2a-streaming-<20位微秒时间戳>` 的 1 个 A2A 实例，
不复用上一次 Streaming Provider case 的实例。真实默认命名空间
`polaris-python-ai-integration`，host 为本机源 IP（离线 `127.0.0.1`），port `1`、
空 protocol、version `1.0.0`、TTL `1`。metadata 包含 `ai-agent-name`、
`ai-agent-card`、`ai-a2a-version=1.0`，卡片 JSONRPC URL 保存动态 HTTP 端口。
离线实例只在 Stub 中；Consumer/Probe 不注册服务或实例。

## 访问与验证链路

Provider 注册 → Probe 校验实例和卡片 → PolarisA2AResolver 发现 → Consumer
根据卡片 URL 调用 `reply_stream` → 收集 TextBlockDeltaEvent 并拼接文本。
依次发送天气与算术问题，断言 Shanghai/Sunny 和 `42`。Tool 只在 Provider
进程内调用，不注册独立 weather/calculate 服务，也不依赖外部模型 API。

验证通过 `--message` 运行非交互路径，不覆盖终端 `launch_console`。结束取消
Provider、等待实例消失、关闭 Context；真实服务对象可保留。产物包含
`console.log`、`verification.log`、`result.json` 和 AI a2a 分类日志。
详见 [Streaming Provider 用例](../streaming_provider/test.md)。
