# Agent Service

This example hosts a native AgentScope `Agent` behind a minimal FastAPI
service. It keeps one Agent per `session_id`, registers the HTTP listener in
Polaris, exposes `/health` and `/chat`, and can load published Polaris Skills.

```bash
python -m examples.agentscope.agent_service.main \
  --address 127.0.0.1:8091 \
  --namespace python-agentscope-e2e \
  --load-skills \
  --skill-name self-improvement
```

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","message":"/skill-list"}'
```

The example focuses on the AgentScope-to-Polaris integration surface. It does
not bundle AgentScope's Redis-backed multi-tenant application deployment.
