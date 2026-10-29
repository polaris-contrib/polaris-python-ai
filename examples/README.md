# Examples

Install Python 3.12+ and the example dependencies from the project root:

```bash
uv venv
uv pip install -e '.[agentscope,a2a]' --group dev
./examples/verify.sh
./examples/verify.sh --only agentscope/skill
./examples/verify.sh --only agentscope/a2a/skill
./examples/verify.sh --only agentscope/mcp
```

The scripts select `POLARIS_PYTHON`, then the project's `.venv/bin/python`,
then uv or python3. They resolve paths independently of the current directory.

Offline verification uses the real SDK, native AgentScope Toolkit and A2AAgent.
Only the Polaris gRPC boundary is replaced. A2A runs a model-free local
JSON-RPC/SSE server on a dynamic port. No model credentials are required.

For a real registry:

```bash
export POLARIS_SERVER_ADDRESS=<host>:8091
export POLARIS_SERVICE_TOKEN=<service-token>
export POLARIS_SKILL_NAME=<published-skill>
export POLARIS_AGENT_SERVICE=<service-with-mounted-skills>
./examples/verify_e2e.sh
```

The namespace defaults to `python-integration`. Skill fixtures must already
exist; these scripts do not publish Skills. A2A test instances are deregistered
before exit. Each scenario retains console output, assertions, results, SDK
logs and backups beneath its own `.logs/` directory.

```bash
./examples/logs.sh --latest --tail 50
./examples/cleanup.sh --dry-run
./examples/cleanup.sh --force
make -C examples verify ARGS="--only agentscope/a2a"
```

Every runnable directory provides `build`, `run`, `package`, `clean`,
`verify` and `verify-e2e` Make targets. Packages include shared example
helpers and extension sources. See [test.md](test.md) for assertions,
environment variables, results and cleanup scope.
