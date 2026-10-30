# 集成示例

在项目根目录安装 Python 3.12+ 和示例依赖：

```bash
uv venv
uv pip install -e '.[agentscope,a2a]' --group dev
./examples/verify.sh
./examples/verify.sh --only agentscope/skill
./examples/verify.sh --only agentscope/a2a/skill
./examples/verify.sh --only agentscope/mcp
```

脚本优先使用 `POLARIS_PYTHON`，其次使用项目 `.venv/bin/python`，
然后使用 uv 或 python3。入口不依赖当前工作目录。

离线验证使用真实 SDK、AgentScope Toolkit 和 A2AAgent，只替换 Polaris
gRPC 边界。A2A 启动本机动态端口的 JSON-RPC/SSE Echo 服务，无需模型密钥。

真实 Polaris 验证：

```bash
export POLARIS_SERVER_ADDRESS=<host>:8091
export POLARIS_SERVICE_TOKEN=<service-token>
export POLARIS_SKILL_NAME=<published-skill>
export POLARIS_AGENT_SERVICE=<service-with-mounted-skills>
./examples/verify_e2e.sh
```

命名空间默认 `python-integration`，由 `POLARIS_E2E_NAMESPACE` 覆盖。
Skill 需事先发布或挂载；脚本只读。A2A 测试退出前反注册实例。
每个场景保留独立的日志、断言、结果、SDK 日志与备份目录。

```bash
./examples/logs.sh --latest --tail 50
./examples/cleanup.sh --dry-run
./examples/cleanup.sh --force
make -C examples verify ARGS="--only agentscope/a2a"
```

含 `main.py` 的目录均提供 `build/run/package/clean/verify/verify-e2e`。
打包包含共享脚手架和扩展源码。验证细节和环境变量见 [test.md](test.md)。
