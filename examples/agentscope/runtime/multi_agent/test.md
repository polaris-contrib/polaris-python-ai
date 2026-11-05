# Runtime Multi-Agent 测试

```bash
./examples/verify.sh --only agentscope/runtime/multi_agent
./examples/verify_e2e.sh --only agentscope/runtime/multi_agent
```

验证一个 Runtime 创建两个 Agent、共享 Toolkit/snapshot、独立对话状态和 AI
日志隔离，并检查 `console.log`、`verification.log`、`result.json`。
