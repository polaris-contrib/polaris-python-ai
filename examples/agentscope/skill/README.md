# Skill Integration

Published loaders list and download Skill ZIPs. Mounted loaders discover
service metadata and load only mounts in the selected namespace.

```bash
./integration/verify.sh --only agentscope/skill
./integration/verify_e2e.sh --only agentscope/skill
```

The [console_agent](console_agent/) example adds an interactive Agent with
dynamic Skill refresh. Set `POLARIS_SKILL_NAME` to choose a published Skill;
otherwise the newer verifier selects the first Skill in the namespace. Mounted
verification still requires `POLARIS_AGENT_SERVICE`. See [test.md](/integration/cases/agentscope/skill/test.md).
