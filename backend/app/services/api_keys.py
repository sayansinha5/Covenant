"""Org API keys. The full key is returned once; only its SHA-256 is stored."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.ids import uuid7
from app.core.security import hash_token, new_opaque_token
from app.models import ApiKey


async def create_key(
    session: AsyncSession, *, org_id: str, user_id: str, name: str
) -> tuple[ApiKey, str]:
    secret = f"ck_{new_opaque_token()}"
    row = ApiKey(
        id=uuid7(),
        org_id=org_id,
        name=name.strip(),
        prefix=secret[:12],
        key_hash=hash_token(secret),
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    return row, secret


async def list_keys(session: AsyncSession, org_id: str) -> list[ApiKey]:
    return list(
        await session.scalars(
            select(ApiKey).where(ApiKey.org_id == org_id).order_by(ApiKey.created_at.desc())
        )
    )


async def revoke_key(session: AsyncSession, *, org_id: str, key_id: str) -> None:
    row = await session.get(ApiKey, key_id)
    if row is None or row.org_id != org_id:
        raise NotFoundError("This API key doesn't exist.", code="API_KEY_NOT_FOUND")
    if row.revoked_at is None:
        from app.db.base import utcnow

        row.revoked_at = utcnow()
