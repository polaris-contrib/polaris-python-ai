# A2A State Resume 测试

```bash
./integration/verify.sh --only agentscope/a2a/state_resume
./integration/verify_e2e.sh --only agentscope/a2a/state_resume
```

测试启动 streaming provider，连续调用 state-resume 两次并检查 context_id
保持一致。验证产物包括 `console.log`、`verification.log` 和 `result.json`。
