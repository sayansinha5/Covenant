# D11 — Don't use the PayPal Agent Toolkit for escrow

**Status:** accepted

**Context.** Escrow needs explicit idempotency keys, audited calls and tight control over state
transitions around every authorize, capture and void.

**Decision.** Covenant calls the PayPal REST APIs directly through its own typed client. The Agent
Toolkit is mentioned in the README as related work.
