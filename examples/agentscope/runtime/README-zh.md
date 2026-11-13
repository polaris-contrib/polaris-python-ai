# PolarisAgentRuntime

演示使用 `PolarisAgentConfig` 和 `PolarisAgentRuntime` 统一装配：

- Skill loader
- A2A registrar / resolver
- 可选 MCP resolver
- Core SDK 与 AI 分类日志
- 借用 `SDKContext` 的生命周期

```bash
./integration/verify.sh --only agentscope/runtime

python examples/agentscope/runtime/main.py \
  --address 127.0.0.1:8091 \
  --skill-name weather \
  --load-skills
```

`--no-skill`、`--no-a2a`、`--mcp` 可切换组件。Runtime 关闭时只释放自己创建的适配器和
AI logger，不销毁传入的 `SDKContext`。

[multi_agent](multi_agent/) 示例使用一个 Runtime 创建两个 Agent，共享
Toolkit 和 Skill 快照，并保持各自对话状态隔离。
