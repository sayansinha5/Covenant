from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ForbiddenError
from app.core.rate_limit import RateLimiter
from app.core.security import InvalidToken, TokenIssuer
from app.db.engine import Database
from app.integrations.paypal import PayPalClient
from app.models import Membership, Organization, User

ActorType = Literal["user", "api_key"]

_bearer = HTTPBearer(auto_error=False)


class NotAuthenticated(AppError):
    status = 401
    code = "NOT_AUTHENTICATED"
    title = "Not authenticated"


@dataclass(frozen=True)
class Principal:
    """Who is calling. Every org-scoped query takes `org_id` from here, never from the request."""

    user_id: str
    org_id: str | None
    role: str | None
    is_platform_admin: bool
    actor_type: ActorType = "user"


@dataclass(frozen=True)
class OrgPrincipal:
    """A principal acting inside one organization (the common case for every tenant route)."""

    user_id: str
    org_id: str
    role: str
    is_platform_admin: bool
    actor_type: ActorType = "user"

    @property
    def can_manage(self) -> bool:
        return self.role in ("owner", "admin")


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_database(request: Request) -> Database:
    database: Database = request.app.state.database
    return database


def get_paypal(request: Request) -> PayPalClient:
    paypal: PayPalClient = request.app.state.paypal
    return paypal


def get_token_issuer(request: Request) -> TokenIssuer:
    issuer: TokenIssuer = request.app.state.token_issuer
    return issuer


async def get_session(database: Database = Depends(get_database)) -> AsyncIterator[AsyncSession]:
    async with database.session() as session:
        yield session


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    issuer: TokenIssuer = Depends(get_token_issuer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if credentials is None:
        raise NotAuthenticated("Sign in to continue.")
    if credentials.credentials.startswith("ck_"):
        return await _principal_from_api_key(session, credentials.credentials)
    try:
        claims = issuer.decode(credentials.credentials)
    except InvalidToken:
        raise NotAuthenticated("Your session has expired. Sign in again.") from None

    user = await session.get(User, claims.user_id)
    if user is None:
        raise NotAuthenticated("Your session has expired. Sign in again.")
    # The role is re-read from the database so a changed or removed membership applies at once.
    role = None
    if claims.org_id is not None:
        role = await session.scalar(
            select(Membership.role).where(
                Membership.user_id == user.id, Membership.org_id == claims.org_id
            )
        )
        if role is None:
            raise NotAuthenticated("Your session has expired. Sign in again.")
    return Principal(
        user_id=user.id,
        org_id=claims.org_id if role else None,
        role=role,
        is_platform_admin=user.is_platform_admin,
    )


async def _principal_from_api_key(session: AsyncSession, token: str) -> Principal:
    from app.core.security import hash_token
    from app.db.base import utcnow
    from app.models import ApiKey

    row = await session.scalar(select(ApiKey).where(ApiKey.key_hash == hash_token(token)))
    if row is None or row.revoked_at is not None:
        raise NotAuthenticated("This API key isn't valid.")
    role = await session.scalar(
        select(Membership.role).where(
            Membership.user_id == row.created_by, Membership.org_id == row.org_id
        )
    )
    user = await session.get(User, row.created_by)
    if role is None or user is None:
        raise NotAuthenticated("This API key isn't valid.")
    row.last_used_at = utcnow()
    await session.commit()
    return Principal(
        user_id=user.id,
        org_id=row.org_id,
        role=role,
        is_platform_admin=user.is_platform_admin,
        actor_type="api_key",
    )


async def require_platform_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.is_platform_admin:
        raise ForbiddenError("Only platform admins can do this.", code="ADMIN_ONLY")
    return principal


async def require_org(principal: Principal = Depends(get_principal)) -> OrgPrincipal:
    if principal.org_id is None or principal.role is None:
        raise ForbiddenError("Create an organization first.", code="ORGANIZATION_REQUIRED")
    return OrgPrincipal(
        user_id=principal.user_id,
        org_id=principal.org_id,
        role=principal.role,
        is_platform_admin=principal.is_platform_admin,
        actor_type=principal.actor_type,
    )


def require_roles(*roles: str) -> Callable[..., object]:
    async def dependency(principal: OrgPrincipal = Depends(require_org)) -> OrgPrincipal:
        if principal.role not in roles:
            raise ForbiddenError("Your role doesn't allow this action.", code="ROLE_FORBIDDEN")
        return principal

    return dependency


require_manager = require_roles("owner", "admin")
require_owner = require_roles("owner")


def money_rate_limit(request: Request, principal: OrgPrincipal = Depends(require_org)) -> None:
    """Money routes are limited per organization, however many people or keys act for it."""
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.hit(request.app.state.settings.rate_limit_money, "money", principal.org_id)


async def current_organization(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> Organization:
    org = await session.get(Organization, principal.org_id)
    if org is None:
        raise NotAuthenticated("Your session has expired. Sign in again.")
    return org


async def require_hirer(org: Organization = Depends(current_organization)) -> Organization:
    if not org.can_hire:
        raise ForbiddenError(
            "Turn on Hire workers for your organization to use this.", code="HIRE_DISABLED"
        )
    return org


async def require_provider(org: Organization = Depends(current_organization)) -> Organization:
    if not org.can_provide:
        raise ForbiddenError(
            "Turn on Provide work for your organization to use this.", code="PROVIDE_DISABLED"
        )
    return org
