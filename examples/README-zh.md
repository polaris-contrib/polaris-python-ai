# 集成示例

本目录只包含可直接运行的 AgentScope 集成示例，作为应用开发者的可执行文档。
验证编排、Registry stub、断言、fixture 和清理逻辑统一放在
[`../integration`](../integration)。

安装 Python 3.12+ 和示例依赖：

```bash
uv sync --all-extras
```

直接运行示例：

```bash
python -m examples.agentscope.a2a.provider.main --address 127.0.0.1:8091
python -m examples.agentscope.a2a.consumer.main --address 127.0.0.1:8091
python -m examples.agentscope.skill.published.main --address 127.0.0.1:8091
python -m examples.agentscope.mcp.agent.main --address 127.0.0.1:8091
python -m examples.agentscope.agent_service.main --address 127.0.0.1:8091
```

每个可运行目录的 Makefile 提供 `build`、`run`、`package` 和 `clean`：

```bash
make -C examples/agentscope/a2a/provider run ARGS="--address 127.0.0.1:8091"
make -C examples/agentscope/mcp/agent run ARGS="--address 127.0.0.1:8091"
```

示例覆盖：

- A2A Provider/Consumer、流式调用、状态恢复和 Skill-backed Agent。
- MCP 元数据解析，以及包含真实 Tool 调用的自包含 MCP Agent。
- Published、Mounted 和 Console Skill 使用方式。
- 单 Agent 与多 Agent Runtime 装配。
- 提供 `/health` 和 `/chat` 的 FastAPI Agent Service。

离线与真实服务验证命令见
[`integration/README.md`](../integration/README.md)。验证、日志和清理命令统一从
`integration/` 执行。
