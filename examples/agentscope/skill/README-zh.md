# Skill 集成

已发布加载器查询列表并下载 Skill ZIP；挂载加载器发现服务元数据，只加载当前
命名空间的挂载内容。两者均通过 AgentScope 原生 Toolkit 读取说明。

```bash
./examples/verify.sh --only agentscope/skill
./examples/verify_e2e.sh --only agentscope/skill
```

[console_agent](console_agent/) 展示交互式 Agent、动态 Skill 刷新和
`launch_console`。真实验证可按需配置 `POLARIS_SKILL_NAME`；
未设置时自动读取目标命名空间中的已发布 Skill。挂载场景仍需
`POLARIS_AGENT_SERVICE`。只读取和下载，不上传或发布 Skill。
见 [test.md](test.md)。
