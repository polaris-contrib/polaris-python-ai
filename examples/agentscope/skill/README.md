# Skill Integration

Published loaders list and download Skill ZIPs. Mounted loaders discover
service metadata and load only mounts in the selected namespace.

```bash
./examples/verify.sh --only agentscope/skill
./examples/verify_e2e.sh --only agentscope/skill
```

Real verification requires an existing published Skill in `POLARIS_SKILL_NAME`
and a service with mounts in `POLARIS_AGENT_SERVICE`. See [test.md](test.md).
