# A2A State Resume

This example persists `A2AAgentState.context_id/task_id` after a
Polaris-discovered A2A conversation and reuses it in later processes.

Registration identity and the real callable endpoint are intentionally
separate; each resumed process resolves the current AgentCard from Polaris.
