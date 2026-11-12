# Architecture

Covenant is an escrow and settlement layer for work done by AI agents and humans. Money is held
in PayPal before work starts, an AI verifier (the Arbiter) checks the delivery against a signed
contract, and deterministic code captures, partly captures or releases the money.

## Processes on localhost

```text
 Browser ──► Frontend (Vite, host :5173)
    │
    └──────► api (FastAPI, :8000) ──► mysql (:3306)
                 │   ▲                   ▲
                 │   │ webhooks          │ outbox jobs (SELECT … FOR UPDATE SKIP LOCKED)
                 │   └── PayPal ◄────────┤
                 │                       │
                 └──► LLM provider     runner ──► PayPal, LLM provider
                                         │
                                         └──► lipi :9101, tally :9102, quickwordz :9103 (A2A)

 MCP client ──► mcp (stdio, on demand) ──► api
```

The browser, the frontend, the API, the runner and the demo workers are separate local processes.
Each one is started with its own command (see the README).

## Layers in the backend

| Layer | Folder | Rule |
| --- | --- | --- |
| HTTP | `app/api/v1/` | Validate input, check roles, call a service. No business rules. |
| Services | `app/services/` | Orchestrate domain rules, repositories and outbox jobs in one transaction. |
| Domain | `app/domain/` | Pure functions: state machine, policy, settlement, reputation. No I/O. |
| Integrations | `app/integrations/` | PayPal and A2A clients. Typed, no business rules, no retries of money calls. |
| Jobs | `app/jobs/` | Outbox handlers run by `runner`; own the retry policy. |
| AI | `app/ai/` | Buyer agent (the only agent), Spec Writer, Arbiter, appeals. Never moves money. |

## How money moves

1. The hirer agrees to a contract; the API writes the state change and an `escrow.create_hold`
   outbox job in the same transaction.
2. The runner creates and authorizes a PayPal order (`intent=AUTHORIZE`) with a deterministic
   `PayPal-Request-Id`, so a retry after a timeout can never create a second hold.
3. After verification, the settlement engine (pure code) turns the verdict into
   capture / void amounts; the runner captures (`final_capture: true`) or voids.
4. The provider is paid with a PayPal payout for `captured − platform fee`.
5. Every PayPal call is recorded in `paypal_operations` with PayPal's debug ID; webhooks and the
   reconciliation job are a second safety net that can only apply valid state transitions.

## PayPal API notes

Checked against PayPal's published OpenAPI specifications (Payments v2, Orders v2, Payouts v1,
Webhooks v1) on 3 Nov 2026:

- PayPal documents no specific error code for voiding an authorization that is already voided.
  `void_authorization` therefore treats a `422` as success only after reading the authorization
  and seeing `VOIDED` (or PayPal reporting `AUTHORIZATION_EXPIRED`).
- Payouts accept `PayPal-Request-Id` (kept 30 days) in addition to the unique `sender_batch_id`,
  so a retried payout replays the original response instead of failing as a duplicate.
- Void may answer `204 No Content`; the client then reads the authorization to return its status.
