from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.core.security import (
    TokenIssuer,
    hash_password,
    hash_token,
    new_opaque_token,
    password_needs_rehash,
    verify_password,
)
from app.db.base import utcnow
from app.models import Membership, Organization, RefreshToken, User
from app.schemas.identity import (
    LoginRequest,
    MembershipOut,
    OrganizationOut,
    SignupRequest,
    UserOut,
)

logger = get_logger("covenant.identity")


class InvalidCredentials(AppError):
    status = 401
    code = "INVALID_CREDENTIALS"
    title = "Sign-in failed"


class AccountLocked(AppError):
    status = 429
    code = "ACCOUNT_LOCKED"
    title = "Too many attempts"


class InvalidRefreshToken(AppError):
    status = 401
    code = "INVALID_REFRESH_TOKEN"
    title = "Session expired"


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    expires_in: int
    refresh_token: str
    user: UserOut


async def primary_membership(
    session: AsyncSession, user_id: str
) -> tuple[Membership, Organization] | None:
    row = (
        await session.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.org_id)
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at)
            .limit(1)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def describe_user(session: AsyncSession, user: User) -> UserOut:
    found = await primary_membership(session, user.id)
    membership = None
    if found:
        member, org = found
        membership = MembershipOut.model_validate(
            {"role": member.role, "organization": OrganizationOut.model_validate(org)}
        )
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_platform_admin=user.is_platform_admin,
        membership=membership,
    )


class IdentityService:
    def __init__(self, session: AsyncSession, settings: Settings, issuer: TokenIssuer) -> None:
        self.session = session
        self.settings = settings
        self.issuer = issuer

    @property
    def _lockout_window(self) -> timedelta:
        return timedelta(minutes=self.settings.login_lockout_minutes)

    async def signup(self, data: SignupRequest) -> IssuedSession:
        user = User(
            id=uuid7(),
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
        )
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError(
                "An account with this email already exists.", code="EMAIL_TAKEN"
            ) from None
        issued = await self._issue(user, family_id=uuid7())
        await self.session.commit()
        logger.info("user_signed_up", user_id=user.id)
        return issued

    async def login(self, data: LoginRequest) -> IssuedSession:
        now = utcnow()
        user = await self.session.scalar(
            select(User).where(User.email == data.email).with_for_update()
        )
        if user is not None and user.locked_until is not None and user.locked_until > now:
            raise AccountLocked(self._locked_message())

        if not verify_password(user.password_hash if user else None, data.password):
            if user is not None:
                locked = self._register_failure(user, now)
                await self.session.commit()
                if locked:
                    logger.warning("login_locked", user_id=user.id)
                    raise AccountLocked(self._locked_message())
            raise InvalidCredentials("Email or password is incorrect.")

        assert user is not None  # noqa: S101  (verify_password is False without a user)
        user.failed_login_count = 0
        user.first_failed_login_at = None
        user.locked_until = None
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(data.password)
        issued = await self._issue(user, family_id=uuid7())
        await self.session.commit()
        return issued

    def _register_failure(self, user: User, now: datetime) -> bool:
        window_started = user.first_failed_login_at
        if window_started is None or now - window_started > self._lockout_window:
            user.first_failed_login_at = now
            user.failed_login_count = 1
        else:
            user.failed_login_count += 1
        if user.failed_login_count >= self.settings.login_max_attempts:
            user.locked_until = now + self._lockout_window
            user.failed_login_count = 0
            user.first_failed_login_at = None
            return True
        return False

    def _locked_message(self) -> str:
        return f"Too many attempts. Try again in {self.settings.login_lockout_minutes} minutes."

    async def refresh(self, raw_token: str) -> IssuedSession:
        now = utcnow()
        current = await self.session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(raw_token))
            .with_for_update()
        )
        if current is None or current.expires_at <= now:
            raise InvalidRefreshToken("Your session has expired. Sign in again.")
        if current.revoked_at is not None or current.replaced_by is not None:
            await self._revoke_family(current.family_id, now)
            await self.session.commit()
            logger.warning("refresh_token_reuse", user_id=current.user_id)
            raise InvalidRefreshToken("Your session has expired. Sign in again.")

        user = await self.session.get(User, current.user_id)
        if user is None:
            raise InvalidRefreshToken("Your session has expired. Sign in again.")
        issued = await self._issue(user, family_id=current.family_id, replacing=current)
        await self.session.commit()
        return issued

    async def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        current = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
        )
        if current is not None:
            await self._revoke_family(current.family_id, utcnow())
            await self.session.commit()

    async def reissue_access(self, user_id: str) -> tuple[str, int]:
        """A new access token after the user's organization or role changed."""
        found = await primary_membership(self.session, user_id)
        member = found[0] if found else None
        return self.issuer.issue(
            user_id=user_id,
            org_id=member.org_id if member else None,
            role=member.role if member else None,
        )

    async def _revoke_family(self, family_id: str, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def _issue(
        self, user: User, *, family_id: str, replacing: RefreshToken | None = None
    ) -> IssuedSession:
        now = utcnow()
        raw = new_opaque_token()
        token = RefreshToken(
            id=uuid7(),
            user_id=user.id,
            family_id=family_id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(days=self.settings.refresh_token_ttl_days),
        )
        self.session.add(token)
        if replacing is not None:
            replacing.replaced_by = token.id
            replacing.revoked_at = now
        access, expires_in = await self.reissue_access(user.id)
        return IssuedSession(
            access_token=access,
            expires_in=expires_in,
            refresh_token=raw,
            user=await describe_user(self.session, user),
        )
