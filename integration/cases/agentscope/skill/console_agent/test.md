# Skill Console Agent 测试

```bash
./integration/verify.sh --only agentscope/skill/console_agent
./integration/verify_e2e.sh --only agentscope/skill/console_agent
```

验证 `/skill-list`、`/skill <name>`、动态刷新、离线快照和 Agent 最终回复。
产物包括 `console.log`、`verification.log` 和 `result.json`。
