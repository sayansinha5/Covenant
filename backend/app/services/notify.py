"""Org-wide notifications. The caller commits."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.models import Notification


def notify(
    session: AsyncSession,
    *,
    org_id: str,
    kind: str,
    title: str,
    body: str,
    link: str | None = None,
) -> None:
    session.add(
        Notification(
            id=uuid7(),
            org_id=org_id,
            kind=kind,
            title=title[:160],
            body=body[:500],
            link=link,
        )
    )
