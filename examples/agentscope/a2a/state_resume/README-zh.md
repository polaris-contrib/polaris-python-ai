# A2A 会话恢复

示例从 Polaris 发现 AgentCard，持久化 `A2AAgentState.context_id/task_id`，
并允许后续进程继续同一个远程会话。实例注册端口与真实调用端口分离，
恢复时仍通过 Polaris 重新发现 AgentCard。

```bash
python examples/agentscope/a2a/state_resume/main.py \
  --address 127.0.0.1:8091 \
  --service streaming-agent \
  --message "first" \
  --message "second"
```
