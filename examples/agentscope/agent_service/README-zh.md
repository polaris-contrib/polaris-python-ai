# Agent Service 示例

示例使用一个精简的 FastAPI 服务承载原生 AgentScope `Agent`。服务按
`session_id` 隔离 Agent，将 HTTP 实例注册到 Polaris，提供 `/health` 和
`/chat`，并可按需加载已发布的 Polaris Skill。

```bash
python -m examples.agentscope.agent_service.main \
  --address 127.0.0.1:8091 \
  --namespace polaris-python-ai-integration \
  --load-skills \
  --skill-name self-improvement
```

该示例聚焦 AgentScope 与 Polaris 的集成面，不包含 AgentScope 基于 Redis 的
多租户完整服务部署。
