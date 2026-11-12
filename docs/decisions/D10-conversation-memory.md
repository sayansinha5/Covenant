# D10 — Conversation memory in our own tables

**Status:** accepted

**Decision.** Assistant conversations live in `agent_conversations` and `agent_messages`
(including the cards that drive the inline UI). The graph is rebuilt on every turn from the last
30 messages; no LangGraph checkpointer.
