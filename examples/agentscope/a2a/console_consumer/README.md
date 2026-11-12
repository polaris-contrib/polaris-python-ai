# Polaris A2A Console Client

This example discovers an AgentCard by Polaris service name and hands the
remote A2A agent to AgentScope `launch_console`, or streams repeated
`--message` inputs non-interactively.

The resolver parses AgentCard 0.3/1.0 according to `ai-a2a-version` and checks
the card interface hosts and version against the discovered instance.
