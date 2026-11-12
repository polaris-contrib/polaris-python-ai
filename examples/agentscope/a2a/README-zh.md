# A2A 集成

Provider 用普通 ProviderAPI 注册一张实例级 AgentCard，默认实例注册端口为 `1`；
Consumer 从实例 metadata 读取 `ai-agent-card` 和 `ai-a2a-version`，再调用
AgentScope 原生 A2AAgent。真实服务端口和 transport 来自 AgentCard。

```bash
./integration/verify.sh --only agentscope/a2a
./integration/verify_e2e.sh --only agentscope/a2a
./integration/verify.sh --only agentscope/a2a/skill
./integration/verify.sh --only agentscope/a2a/streaming_provider
./integration/verify.sh --only agentscope/a2a/state_resume
```

该目录还包含流式 Tool Calling Provider、`launch_console` Consumer 和
`A2AAgentState` 会话恢复示例。

Provider 也可通过 `--registration-port` 覆盖注册身份端口。同 IP 并行版本必须使用
不同注册端口，不能依赖实例端口作为 A2A 调用地址。

真实验证需 `POLARIS_SERVER_ADDRESS`，服务 token 可为空。
使用唯一服务名、本机动态端口和 TTL 1 秒，验证注册、发现、调用和退出反注册。
细节见 [test.md](/integration/cases/agentscope/a2a/test.md)。
