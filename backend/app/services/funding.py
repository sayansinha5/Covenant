from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.core.security import hash_token, new_opaque_token
from app.db.base import utcnow
from app.integrations.paypal import PayPalClient, PayPalError
from app.integrations.paypal.audit import Operation
from app.models import PayPalFundingAccount, PayPalVaultSession
from app.schemas.funding import FundingAccountOut

VAULT_SESSION_TTL = timedelta(minutes=30)
RETURN_PATH = "/api/v1/paypal/vault/return"

logger = get_logger("covenant.funding")


class PayPalUnavailable(AppError):
    status = 502
    code = "PAYPAL_ERROR"
    title = "PayPal error"


class PayPalNotReady(AppError):
    status = 503
    code = "PAYPAL_NOT_CONFIGURED"
    title = "PayPal not configured"


@dataclass(frozen=True)
class VaultStart:
    session_id: str
    approve_url: str


class FundingService:
    def __init__(self, session: AsyncSession, settings: Settings, paypal: PayPalClient) -> None:
        self.session = session
        self.settings = settings
        self.paypal = paypal

    @property
    def mode(self) -> str:
        return self.settings.paypal_funding_mode

    async def connected_account(self, org_id: str) -> PayPalFundingAccount | None:
        return await self.session.scalar(
            select(PayPalFundingAccount).where(
                PayPalFundingAccount.org_id == org_id,
                PayPalFundingAccount.mode == self.mode,
                PayPalFundingAccount.status == "connected",
            )
        )

    async def is_connected(self, org_id: str) -> bool:
        # In approve_each mode the payer approves every hold in PayPal; nothing is stored.
        if self.mode == "approve_each":
            return self.paypal.config.configured
        return await self.connected_account(org_id) is not None

    async def describe(self, org_id: str) -> FundingAccountOut:
        account = await self.connected_account(org_id)
        return FundingAccountOut(
            mode=self.settings.paypal_funding_mode,
            connected=await self.is_connected(org_id),
            payer_email=account.payer_email if account else None,
            connected_at=account.created_at if account else None,
        )

    def _require_vault(self) -> None:
        if not self.paypal.config.configured:
            raise PayPalNotReady(
                "PayPal isn't configured on this server. Set the sandbox credentials in "
                "backend/.env."
            )
        if self.mode != "vault":
            raise ConflictError(
                "This server approves each hold in PayPal, so there's no account to connect.",
                code="VAULT_DISABLED",
            )

    async def start_vault(self, *, org_id: str, user_id: str, return_path: str) -> VaultStart:
        self._require_vault()
        state = new_opaque_token()
        vault_session = PayPalVaultSession(
            id=uuid7(),
            org_id=org_id,
            user_id=user_id,
            state_hash=hash_token(state),
            return_path=return_path,
            status="pending",
            expires_at=utcnow() + VAULT_SESSION_TTL,
        )
        self.session.add(vault_session)
        await self.session.commit()

        callback = f"{self.paypal.config.return_base_url}{RETURN_PATH}?state={state}"
        try:
            setup = await self.paypal.create_setup_token(
                operation=Operation("vault_setup", f"cov-vault-{vault_session.id}-setup"),
                return_url=callback,
                cancel_url=f"{callback}&outcome=cancel",
            )
        except PayPalError as exc:
            await self._fail(vault_session, "PayPal couldn't start the connection.")
            logger.warning("vault_start_failed", session_id=vault_session.id, error=str(exc))
            raise PayPalUnavailable(
                "PayPal couldn't start the connection. Try again in a moment."
            ) from exc
        if not setup.approve_url:
            await self._fail(vault_session, "PayPal didn't return an approval link.")
            raise PayPalUnavailable("PayPal didn't return an approval link. Try again.")

        vault_session.setup_token_id = setup.id
        await self.session.commit()
        return VaultStart(session_id=vault_session.id, approve_url=setup.approve_url)

    async def complete_vault(self, state: str, *, cancelled: bool) -> PayPalVaultSession | None:
        """Handles PayPal's redirect back. Safe to call twice: only a pending session acts."""
        vault_session = await self.session.scalar(
            select(PayPalVaultSession)
            .where(PayPalVaultSession.state_hash == hash_token(state))
            .with_for_update()
        )
        if vault_session is None or vault_session.status != "pending":
            return vault_session
        if vault_session.expires_at <= utcnow() or vault_session.setup_token_id is None:
            await self._fail(vault_session, "The connection took too long. Start again.")
            return vault_session
        if cancelled:
            vault_session.status = "cancelled"
            await self.session.commit()
            return vault_session

        try:
            token = await self.paypal.create_payment_token(
                vault_session.setup_token_id,
                operation=Operation("vault_token", f"cov-vault-{vault_session.id}-token"),
            )
        except PayPalError as exc:
            logger.warning("vault_exchange_failed", session_id=vault_session.id, error=str(exc))
            await self._fail(vault_session, "PayPal didn't confirm the connection.")
            return vault_session

        previous = await self.connected_account(vault_session.org_id)
        if previous is not None:
            previous.status = "disconnected"
        self.session.add(
            PayPalFundingAccount(
                id=uuid7(),
                org_id=vault_session.org_id,
                mode="vault",
                paypal_customer_id=token.customer_id,
                vault_token_id=token.id,
                payer_email=token.payer_email,
                status="connected",
            )
        )
        vault_session.status = "connected"
        await self.session.commit()
        logger.info("vault_connected", org_id=vault_session.org_id)
        if previous is not None and previous.vault_token_id:
            await self._delete_token_quietly(previous.vault_token_id)
        return vault_session

    async def get_session(self, org_id: str, session_id: str) -> PayPalVaultSession:
        vault_session = await self.session.scalar(
            select(PayPalVaultSession).where(
                PayPalVaultSession.id == session_id, PayPalVaultSession.org_id == org_id
            )
        )
        if vault_session is None:
            raise NotFoundError("Connection attempt not found.")
        return vault_session

    async def cancel_session(self, org_id: str, session_id: str) -> PayPalVaultSession:
        vault_session = await self.get_session(org_id, session_id)
        if vault_session.status == "pending":
            vault_session.status = "cancelled"
            await self.session.commit()
        return vault_session

    async def disconnect(self, org_id: str) -> None:
        account = await self.connected_account(org_id)
        if account is None:
            return
        if account.vault_token_id:
            try:
                await self.paypal.delete_payment_token(account.vault_token_id)
            except PayPalError as exc:
                raise PayPalUnavailable(
                    "PayPal couldn't remove the saved account. Try again in a moment."
                ) from exc
        account.status = "disconnected"
        await self.session.commit()

    async def _fail(self, vault_session: PayPalVaultSession, reason: str) -> None:
        vault_session.status = "failed"
        vault_session.failure_reason = reason
        await self.session.commit()

    async def _delete_token_quietly(self, token_id: str) -> None:
        try:
            await self.paypal.delete_payment_token(token_id)
        except PayPalError as exc:
            logger.warning("vault_old_token_delete_failed", error=str(exc))
