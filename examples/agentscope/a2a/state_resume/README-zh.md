# A2A 会话恢复

示例从 Polaris 发现 AgentCard，持久化 `A2AAgentState.context_id/task_id`，
并允许后续进程继续同一个远程会话。

```bash
python examples/agentscope/a2a/state_resume/main.py \
  --address 1.14.219.4:8091 \
  --service streaming-agent \
  --message "first" \
  --message "second"
```
