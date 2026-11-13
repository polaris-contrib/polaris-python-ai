# 单 Runtime 多 Agent

示例使用一个 `PolarisAgentRuntime` 创建多个 Agent：

- 共享 SDKContext、Toolkit 和 Polaris Skill snapshot
- 每个 Agent 拥有独立对话状态
- 两个 Agent 都能读取最新 Skill 内容

```bash
python examples/agentscope/runtime/multi_agent/main.py \
  --address 127.0.0.1:8091 \
  --skill-name weather
```
