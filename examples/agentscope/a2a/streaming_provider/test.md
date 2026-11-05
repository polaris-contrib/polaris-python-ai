# Streaming A2A Provider 测试

```bash
./examples/verify.sh --only agentscope/a2a/streaming_provider
./examples/verify_e2e.sh --only agentscope/a2a/streaming_provider
```

验证 context 隔离、流式 artifact、weather/calculate/time Tool、Polaris
注册/发现/反注册、AI 分类日志和运行产物 `console.log`、`verification.log`、
`result.json`。
