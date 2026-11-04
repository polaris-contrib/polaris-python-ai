# Skill 驱动的 A2A

无需模型密钥即可运行完整 AgentScope 链路。Provider 将已发布或挂载的
Polaris Skill 装入原生 `Agent` 和 `Toolkit`，通过 A2A 暴露并注册到 Polaris；
Consumer 发现 AgentCard，并在同一个原生 A2A 客户端上完成多轮调用。

```bash
../../verify.sh --only agentscope/a2a/skill
```

手动启动 provider：

```bash
python -m examples.agentscope.a2a.skill.main --address 127.0.0.1:8091 \
  --service-token <token> --skill-name weather
```

Provider 支持 `--skill-source published` 和 `--skill-source mounted`。已发布
模式使用 `--skill-name`、`--skill-version`；挂载模式使用 `--skill-service`，
未指定时回退到注册的 Agent 名称。本地路由模型支持 `/skill-list`、
`/skill <name>`，其他输入回显。
