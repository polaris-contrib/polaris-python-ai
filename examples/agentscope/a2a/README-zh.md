# A2A 集成

Provider 用普通 ProviderAPI 注册无模型的 JSON-RPC/SSE Echo 服务，
Consumer 从实例元数据解析 AgentCard，调用 AgentScope 原生 A2AAgent。

```bash
./examples/verify.sh --only agentscope/a2a
./examples/verify_e2e.sh --only agentscope/a2a
./examples/verify.sh --only agentscope/a2a/skill
```

真实验证需 `POLARIS_SERVER_ADDRESS` 和 `POLARIS_SERVICE_TOKEN`。
使用唯一服务名、本机动态端口和 TTL 1 秒，验证注册、发现、调用和退出反注册。
细节见 [test.md](test.md)。
