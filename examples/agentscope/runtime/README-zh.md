# PolarisAgentRuntime

演示使用 `PolarisAgentConfig` 和 `PolarisAgentRuntime` 统一装配：

- Skill loader
- A2A registrar / resolver
- 可选 MCP resolver
- Core SDK 与 AI 分类日志
- 借用 `SDKContext` 的生命周期

```bash
./examples/verify.sh --only agentscope/runtime

python examples/agentscope/runtime/main.py \
  --address 127.0.0.1:8091 \
  --skill-name weather \
  --load-skills
```

`--no-skill`、`--no-a2a`、`--mcp` 可切换组件。Runtime 关闭时只释放自己创建的适配器和
AI logger，不销毁传入的 `SDKContext`。
