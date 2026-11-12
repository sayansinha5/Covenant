# D7 — Workers speak A2A

**Status:** accepted

**Decision.** Covenant is an A2A client and each demo worker is an A2A server, both built on the
official `a2a-sdk` package. Discovery via `/.well-known/agent-card.json`, dispatch via
`message/send`, progress via `tasks/get`.

**Fallback.** Plain REST (`POST /tasks`, `GET /tasks/{id}`) with the same task lifecycle.
