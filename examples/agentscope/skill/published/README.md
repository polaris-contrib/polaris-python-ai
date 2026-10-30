# Published Example

Run from the project root after installing the example dependencies:

```bash
python -m examples.agentscope.skill.published.main --address <host>:8091 --name weather --version v1
make -C examples/agentscope/skill/published verify
```

Use `--config examples/agentscope/polaris.yaml` to start from YAML.
`make build` creates `bin`; `make package` creates `.build/published.tar.gz`
with shared helpers; `make clean` removes build products. Logs and backups
are kept per run. See [test.md](test.md) and the parent documentation.
