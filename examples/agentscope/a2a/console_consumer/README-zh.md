# Polaris A2A Console Client

该示例只提供服务名，通过 Polaris 发现 AgentCard，并将远程 Agent 交给
AgentScope `launch_console`：

```bash
python examples/agentscope/a2a/console_consumer/main.py \
  --address 1.14.219.4:8091 \
  --service streaming-agent
```

自动化模式可重复传 `--message`，直接使用 `reply_stream()` 消费流式文本。
