from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import httpx

from app.integrations.paypal import authorizations, orders, payouts, vault, webhooks
from app.integrations.paypal.audit import Operation, OperationRecorder
from app.integrations.paypal.config import PayPalConfig
from app.integrations.paypal.http import PayPalHttp
from app.integrations.paypal.types import (
    Authorization,
    Capture,
    Order,
    PaymentToken,
    PayoutBatch,
    SetupToken,
)


class PayPalClient:
    """The one entry point the rest of Covenant uses for PayPal. Create one per process."""

    def __init__(
        self,
        config: PayPalConfig,
        *,
        http: httpx.AsyncClient | None = None,
        recorder: OperationRecorder | None = None,
    ) -> None:
        self.transport = PayPalHttp(config, http=http, recorder=recorder)

    @property
    def config(self) -> PayPalConfig:
        return self.transport.config

    async def aclose(self) -> None:
        await self.transport.aclose()

    # ── Orders ──────────────────────────────────────────
    async def create_authorize_order(
        self,
        *,
        operation: Operation,
        amount: Decimal,
        reference_id: str,
        custom_id: str,
        invoice_id: str,
        description: str,
        vault_id: str | None = None,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> Order:
        return await orders.create_authorize_order(
            self.transport,
            operation=operation,
            amount=amount,
            reference_id=reference_id,
            custom_id=custom_id,
            invoice_id=invoice_id,
            description=description,
            vault_id=vault_id,
            return_url=return_url,
            cancel_url=cancel_url,
        )

    async def authorize_order(self, order_id: str, *, operation: Operation) -> Order:
        return await orders.authorize_order(self.transport, order_id, operation=operation)

    async def get_order(self, order_id: str) -> Order:
        return await orders.get_order(self.transport, order_id)

    # ── Authorizations ──────────────────────────────────
    async def get_authorization(self, authorization_id: str) -> Authorization:
        return await authorizations.get_authorization(self.transport, authorization_id)

    async def capture_authorization(
        self,
        authorization_id: str,
        *,
        operation: Operation,
        amount: Decimal,
        invoice_id: str,
        note_to_payer: str,
        final_capture: bool = True,
    ) -> Capture:
        return await authorizations.capture_authorization(
            self.transport,
            authorization_id,
            operation=operation,
            amount=amount,
            invoice_id=invoice_id,
            note_to_payer=note_to_payer,
            final_capture=final_capture,
        )

    async def void_authorization(
        self, authorization_id: str, *, operation: Operation
    ) -> Authorization:
        return await authorizations.void_authorization(
            self.transport, authorization_id, operation=operation
        )

    async def reauthorize_authorization(
        self, authorization_id: str, *, operation: Operation, amount: Decimal
    ) -> Authorization:
        return await authorizations.reauthorize_authorization(
            self.transport, authorization_id, operation=operation, amount=amount
        )

    # ── Payouts ─────────────────────────────────────────
    async def create_payout(
        self,
        *,
        payout_id: str,
        contract_id: str | None,
        receiver_email: str,
        amount: Decimal,
        sender_item_id: str,
        note: str,
        email_subject: str,
    ) -> PayoutBatch:
        return await payouts.create_payout(
            self.transport,
            payout_id=payout_id,
            contract_id=contract_id,
            receiver_email=receiver_email,
            amount=amount,
            sender_item_id=sender_item_id,
            note=note,
            email_subject=email_subject,
        )

    async def get_payout_batch(self, payout_batch_id: str) -> PayoutBatch:
        return await payouts.get_payout_batch(self.transport, payout_batch_id)

    # ── Vault ───────────────────────────────────────────
    async def create_setup_token(
        self, *, operation: Operation, return_url: str, cancel_url: str
    ) -> SetupToken:
        return await vault.create_setup_token(
            self.transport, operation=operation, return_url=return_url, cancel_url=cancel_url
        )

    async def create_payment_token(
        self, setup_token_id: str, *, operation: Operation
    ) -> PaymentToken:
        return await vault.create_payment_token(self.transport, setup_token_id, operation=operation)

    async def delete_payment_token(self, payment_token_id: str) -> None:
        await vault.delete_payment_token(self.transport, payment_token_id)

    # ── Webhooks ────────────────────────────────────────
    async def verify_webhook_signature(
        self, headers: Mapping[str, str], event: dict[str, Any]
    ) -> bool:
        return await webhooks.verify_webhook_signature(self.transport, headers, event)
