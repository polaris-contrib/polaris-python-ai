# 流式 Tool-Calling A2A Provider

该示例将 AgentScope Agent 暴露为 A2A 1.0 服务：

- 每个 A2A `context_id` 创建独立 Agent
- 流式输出 `TextBlockDeltaEvent` 至 A2A artifact
- 支持 weather、calculate 和 current-time 普通 Tool
- 通过 Polaris 注册服务、心跳和反注册
- 可选加载 published/mounted Skill

```bash
python examples/agentscope/a2a/streaming_provider/main.py \
  --address 1.14.219.4:8091 \
  --service streaming-agent \
  --skill-source none
```
