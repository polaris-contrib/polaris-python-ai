# Provider Example

Run from the project root after installing the example dependencies:

```bash
python -m examples.agentscope.a2a.provider.main \
  --address <host>:8091 \
  --service order-agent \
  --host <reachable-ip> \
  --multi-protocol \
  --agent-version 2.1.0
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
`--multi-protocol` serves JSONRPC 1.0 at `/a2a/v1`, JSONRPC 0.3 at
`/a2a/legacy`, and HTTP+JSON 1.0 at `/rest`. All URLs use the same instance IP
and still produce one Polaris instance. GRPC is not advertised until the
example has a callable gRPC server.

To verify and retain the registered Provider until cleanup:

```bash
./integration/verify_e2e.sh --only agentscope/a2a/provider --retain
./integration/cleanup.sh --dry-run
./integration/cleanup.sh --force
```

`--retain` launches the Provider as an independently recorded process. After
verification it keeps heartbeating until cleanup terminates it; graceful
termination deregisters the instance.

To run parallel v1/v2 instances on one IP, give the processes distinct
registration ports: omit the option for the first process to use the default `1`,
and use `--registration-port 18080` for the second. The value controls instance identity and
replacement, not the callable port in the AgentCard.
