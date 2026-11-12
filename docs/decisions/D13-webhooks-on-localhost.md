# D13 — Webhooks through a developer-started tunnel

**Status:** accepted

**Decision.** The developer runs ngrok or cloudflared and registers
`https://<tunnel-host>/api/v1/webhooks/paypal` in the sandbox app. Webhooks are a safety net: every
PayPal call's response already updates state directly, so the app works without a tunnel.

**Fallback.** The reconciliation job (every 5 minutes) compares state with PayPal.
