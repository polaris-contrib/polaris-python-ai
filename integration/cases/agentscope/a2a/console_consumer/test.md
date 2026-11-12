# A2A Console Consumer 测试

```bash
./integration/verify.sh --only agentscope/a2a/console_consumer
./integration/verify_e2e.sh --only agentscope/a2a/console_consumer
```

启动配套 streaming provider，通过 Polaris 发现 AgentCard，验证流式多轮文本、
Tool 调用和无模型 API key 的离线链路。运行产物包含 `console.log`、
`verification.log` 和 `result.json`。
