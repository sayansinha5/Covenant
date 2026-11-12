# D6 — JWT access token in memory, rotating refresh cookie

**Status:** accepted

**Decision.** A 15-minute JWT access token kept in browser memory, plus a 7-day refresh token in
an `HttpOnly`, `SameSite=Strict` cookie scoped to `/api/v1/auth`. Refresh tokens rotate on every
use; reusing an old one revokes the whole token family.
