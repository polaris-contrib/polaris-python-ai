# Provider Example

Run from the project root after installing the example dependencies:

```bash
python -m examples.agentscope.a2a.provider.main \
  --address <host>:8091 \
  --service echo-agent \
  --host <reachable-ip> \
  --registration-port 1 \
  --multi-interface
./integration/verify.sh --only agentscope/a2a/provider
```

Use `--config examples/agentscope/polaris.yaml` to start from YAML.
Use `--skill-source published --skill-name weather` or
`--skill-source mounted --skill-service weather-agent` to expose a model-free
Skill-backed Agent that answers `/skill-list`, `/skill <name>`, and echoes other
input.
`make build` creates `bin`; `make package` creates `.build/provider.tar.gz`
with shared helpers; `make clean` removes build products. Logs and backups
are kept per run. See [test.md](/integration/cases/agentscope/a2a/provider/test.md) and the parent documentation.
`--registration-port` is the Polaris instance identity port, not the real A2A
listener port stored in the AgentCard URL.
`--multi-interface` serves JSONRPC and HTTP+JSON on the same listener while
still registering exactly one Polaris instance.

To run parallel v1/v2 instances on one IP, give the processes distinct
registration ports, such as `--registration-port 1` and
`--registration-port 18080`. The value controls instance identity and
replacement, not the callable port in the AgentCard.
