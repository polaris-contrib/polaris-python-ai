# Verification

Offline:

```bash
../../verify.sh --only agentscope/a2a/skill
```

Real registry:

```bash
../../verify_e2e.sh --only agentscope/a2a/skill
```

The offline check starts one provider with a published Skill and another with
a mounted Skill. Each run verifies Polaris registration and automatic
heartbeat, then invokes `/skill-list` and `/skill <name>` through discovery.
It asserts both replies, deregistration, listener shutdown, and stopped
Context background threads. Logs and retained results are under
`.logs/<run>/console.log`, `result.json`, and `verification.log`.

Real verification requires `POLARIS_SERVER_ADDRESS`,
`POLARIS_E2E_SERVICE_TOKEN`, and `POLARIS_SKILL_NAME`. Set
`POLARIS_AGENT_SERVICE` to use a mounted Skill instead of a published one.
