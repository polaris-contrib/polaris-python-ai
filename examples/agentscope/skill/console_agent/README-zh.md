# Polaris Skill Console Agent

使用 `launch_console` 运行一个长期存活的 Agent：

- `PolarisSkillLoader` 加载 published 或 mounted Skill
- `PolarisDynamicSkillMiddleware` 每轮刷新并保留成功快照
- 模型不可用时使用本地 DemoChatModel

```bash
python examples/agentscope/skill/console_agent/main.py \
  --address 1.14.219.4:8091 \
  --skill-name weather
```
