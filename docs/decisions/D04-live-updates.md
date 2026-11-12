# D4 — Streaming for the assistant, polling for contracts

**Status:** accepted

**Decision.** The assistant answers `POST /assistant/conversations/{id}/messages` with
`text/event-stream`, read by axios `onDownloadProgress` and an incremental SSE frame parser.
Contract detail pages poll every `VITE_CONTRACT_POLL_MS` (2 s) while the contract is
non-terminal. No WebSockets.

**Fallback.** Polling for the assistant too.
