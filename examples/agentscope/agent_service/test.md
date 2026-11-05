# Agent Service 测试

```bash
./examples/verify.sh --only agentscope/agent_service
./examples/verify_e2e.sh --only agentscope/agent_service
```

验证启动真实 HTTP 监听器、注册成功、`/health`、两个独立 session 的
`/chat`、Polaris Skill 加载、反注册和监听器关闭。每次运行保留
`console.log`、`verification.log`、`result.json` 以及 Core SDK 和 AI 分类日志。
