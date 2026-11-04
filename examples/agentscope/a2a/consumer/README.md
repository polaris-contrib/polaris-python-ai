# Consumer Example

Run from the project root after installing the example dependencies:

```bash
python -m examples.agentscope.a2a.consumer.main --address <host>:8091 --service echo-agent --message 'Hello Polaris'
make -C examples/agentscope/a2a/consumer verify
```

Use `--config examples/agentscope/polaris.yaml` to start from YAML.
Repeat `--message` for a multi-turn conversation; the native A2A client is reused.
`make build` creates `bin`; `make package` creates `.build/consumer.tar.gz`
with shared helpers; `make clean` removes build products. Logs and backups
are kept per run. See [test.md](test.md) and the parent documentation.
