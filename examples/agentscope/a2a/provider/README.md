# Provider Example

Run from the project root after installing the example dependencies:

```bash
python -m examples.agentscope.a2a.provider.main --address <host>:8091 --service echo-agent --host <reachable-ip>
make -C examples/agentscope/a2a/provider verify
```

Use `--config examples/agentscope/polaris.yaml` to start from YAML.
Use `--skill-source published --skill-name weather` or
`--skill-source mounted --skill-service weather-agent` to expose a model-free
Skill-backed Agent that answers `/skill-list`, `/skill <name>`, and echoes other
input.
`make build` creates `bin`; `make package` creates `.build/provider.tar.gz`
with shared helpers; `make clean` removes build products. Logs and backups
are kept per run. See [test.md](test.md) and the parent documentation.
