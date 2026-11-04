# Mounted Example

Run from the project root after installing the example dependencies:

```bash
python -m examples.agentscope.skill.mounted.main --address <host>:8091 --service weather-agent
make -C examples/agentscope/skill/mounted verify
```

Use `--config examples/agentscope/polaris.yaml` to start from YAML.
`make build` creates `bin`; `make package` creates `.build/mounted.tar.gz`
with shared helpers; `make clean` removes build products. Logs and backups
are kept per run. See [test.md](test.md) and the parent documentation.
