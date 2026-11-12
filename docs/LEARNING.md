# What this codebase taught

Covenant is the story of Riya hiring Lipi, Tally, QuickWordz and Arjun. PayPal holds the money.
An Arbiter decides whether the work passed. The model never chooses the amount that moves.

## The path of one dollar

Riya agrees in the Contract Review modal. That is the only click that asks PayPal to hold funds.
The assistant can draft the contract and explain the mandate, and it has no fund tool. The hold
job, the capture job and the void job are the only code that talks to PayPal about money, and
they read amounts from the settlement engine. A verdict of pass captures the hold, partial
captures `held * pass ratio` rounded down, and fail or manipulation voids it.

## Why the Arbiter is a graph with a boring ending

The graph loads the delivery, splits it into items, runs the hard checks, scans for hidden text
and reviewer-directed phrases, asks a model for scores, and then stops being a model. The Decide
step is ordinary code that maps a ratio onto the bands stored in the spec. A second opinion can
only force `needs_review`. It cannot capture a different amount by itself. That split is the
whole point: the model can be wrong, persuasive or manipulated, and the cents still come from
`app/domain/settlement.py`.

## Workers are untrusted

Lipi, Tally and QuickWordz are A2A servers. Covenant fetches the agent card and sends one JSON
task with a bearer token. The URL is checked before any request: http or https, no userinfo, the
host on the allow list, and link-local addresses blocked even if someone lists them. The delivery
is stored as data. The UI does not render it as HTML, which is why a hidden comment is evidence
rather than a script.

## The outbox is the retry boundary

Dispatch, verification, capture and payout are rows in `outbox_jobs`, written in the same
transaction as the contract change that required them. The runner locks a job with `SKIP LOCKED`,
so two runners don't do the same capture. If the process dies after PayPal accepted a capture
but before Covenant recorded it, the job runs again with the same PayPal request id and PayPal
returns the original capture. That is why money jobs must be safe to run twice.

## What to read next

Start at `app/domain/state_machine.py` for the legal moves, then `app/services/execution.py` for
how a funded contract becomes a verdict, then `app/services/escrow.py` for the PayPal calls.
`app/ai/arbiter/pipeline.py` is the graph. `app/ai/buyer/agent.py` is the assistant, and the
absence of a fund tool there is deliberate.
