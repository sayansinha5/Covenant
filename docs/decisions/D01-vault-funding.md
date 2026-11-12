# D1 — Fund holds from a vaulted PayPal wallet

**Status:** accepted

**Context.** Mira funds escrow on the hirer's behalf. A PayPal popup for every contract would
break the "agent hires agent" flow.

**Options.** (a) Vault v3: setup token → payment token, then orders use `vault_id`.
(b) The buyer approves every order in a popup.

**Decision.** (a). The hirer connects PayPal once during onboarding; holds are created with
`payment_source.paypal.vault_id` and PayPal authorizes them immediately.

**Fallback.** `PAYPAL_FUNDING_MODE=approve_each` creates the order with return/cancel URLs and the
Contract Review modal opens the `payer-action` link. Everything after authorization is identical.
