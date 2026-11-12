# D2 — Only the buyer agent is an agent

**Status:** accepted

**Context.** Open-ended tool-calling loops are harder to test and audit than fixed pipelines.
Money decisions must be deterministic.

**Decision.** Mira (the buyer agent) is the only LangGraph tool-calling agent. The Spec Writer,
Arbiter, second opinion and appeal memo are fixed pipelines that use LangChain structured
output. The Arbiter is a `StateGraph` with deterministic edges.
