# Skill 集成

已发布加载器查询列表并下载 Skill ZIP；挂载加载器发现服务元数据，只加载当前
命名空间的挂载内容。两者均通过 AgentScope 原生 Toolkit 读取说明。

```bash
./examples/verify.sh --only agentscope/skill
./examples/verify_e2e.sh --only agentscope/skill
```

真实验证需预先配置 `POLARIS_SKILL_NAME` 和 `POLARIS_AGENT_SERVICE`。
只读取和下载，不上传或发布 Skill。见 [test.md](test.md)。
