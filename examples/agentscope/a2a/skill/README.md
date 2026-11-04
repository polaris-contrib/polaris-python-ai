# Skill-Backed A2A

Run the full AgentScope chain without a model API key. The provider loads a
published or mounted Polaris Skill into a native `Agent` and `Toolkit`, exposes
it through A2A, and registers the endpoint in Polaris. The consumer discovers
the card and keeps one native A2A client for a multi-turn conversation.

```bash
../../verify.sh --only agentscope/a2a/skill
```

Manual provider:

```bash
python -m examples.agentscope.a2a.skill.main --address 127.0.0.1:8091 \
  --service-token <token> --skill-name weather
```

Use the provider's `--skill-source published` or `--skill-source mounted`
options. Published mode accepts `--skill-name` and `--skill-version`; mounted
mode accepts `--skill-service` and falls back to the registered Agent name.
The model-free router answers `/skill-list`, `/skill <name>`, and otherwise
echoes the input.
