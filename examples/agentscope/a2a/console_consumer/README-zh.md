# Polaris A2A Console Client

该示例只提供服务名，通过 Polaris 发现 AgentCard，并将远程 Agent 交给
AgentScope `launch_console`：

Resolver 会按 `ai-a2a-version` 解析 0.3/1.0 卡片，校验 interface host
与实例 host、实例 version 与卡片 version 一致；调用端口来自 AgentCard。

```bash
python examples/agentscope/a2a/console_consumer/main.py \
  --address 127.0.0.1:8091 \
  --service streaming-agent
```

自动化模式可重复传 `--message`，直接使用 `reply_stream()` 消费流式文本。
