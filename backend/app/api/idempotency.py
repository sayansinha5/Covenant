"""Client-supplied `Idempotency-Key` for money routes. The key row is inserted in the same
transaction as the money change and holds the stored response, so:

- a retry after the response was lost replays the original response;
- a concurrent duplicate blocks on the key's primary key until the first request commits,
  then replays its response;
- a failed request rolls back the key too, so the client may retry it."""

import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgPrincipal, require_org
from app.core.errors import AppError
from app.db.base import utcnow
from app.models import IdempotencyKey

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,100}$")
KEY_TTL = timedelta(hours=24)
PENDING_STATUS = 0


class IdempotencyKeyInvalid(AppError):
    status = 400
    code = "IDEMPOTENCY_KEY_REQUIRED"
    title = "Idempotency key required"


class IdempotencyKeyReused(AppError):
    status = 422
    code = "IDEMPOTENCY_KEY_REUSED"
    title = "Idempotency key reused"


@dataclass(frozen=True, slots=True)
class IdempotentRequest:
    org_id: str
    route: str
    key: str
    request_hash: str


async def idempotent_request(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: OrgPrincipal = Depends(require_org),
) -> IdempotentRequest:
    if idempotency_key is None or not KEY_PATTERN.fullmatch(idempotency_key):
        raise IdempotencyKeyInvalid(
            "Send an Idempotency-Key header (8 to 100 letters, digits or -_.:) with this request."
        )
    body = await request.body()
    digest = hashlib.sha256()
    for part in (request.method.encode(), request.url.path.encode(), body):
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return IdempotentRequest(
        org_id=principal.org_id,
        route=request.scope["route"].path,
        key=idempotency_key,
        request_hash=digest.hexdigest(),
    )


async def replay_or_reserve(
    session: AsyncSession, request: IdempotentRequest
) -> JSONResponse | None:
    """Return the stored response for a repeated request, or reserve the key (uncommitted) and
    return None so the caller does the work and then calls `remember`."""
    pk = (request.org_id, request.route, request.key)
    existing = await session.get(IdempotencyKey, pk)
    if existing is not None and existing.created_at < utcnow() - KEY_TTL:
        await session.delete(existing)
        await session.flush()
        existing = None
    if existing is None:
        session.add(
            IdempotencyKey(
                org_id=request.org_id,
                route=request.route,
                key=request.key,
                request_hash=request.request_hash,
                response_status=PENDING_STATUS,
                response_body={},
            )
        )
        try:
            await session.flush()
        except IntegrityError:
            # A concurrent request with this key committed first.
            await session.rollback()
            existing = await session.get(IdempotencyKey, pk, populate_existing=True)
        else:
            return None
    if existing is None or existing.response_status == PENDING_STATUS:
        raise RuntimeError("An idempotency key row is visible without its response")
    if existing.request_hash != request.request_hash:
        raise IdempotencyKeyReused(
            "This Idempotency-Key was already used for a different request. Use a new key."
        )
    return JSONResponse(
        existing.response_body,
        status_code=existing.response_status,
        headers={"Idempotent-Replayed": "true"},
    )


async def remember(
    session: AsyncSession, request: IdempotentRequest, status: int, body: dict[str, Any]
) -> JSONResponse:
    row = await session.get_one(IdempotencyKey, (request.org_id, request.route, request.key))
    row.response_status = status
    row.response_body = body
    return JSONResponse(body, status_code=status)
