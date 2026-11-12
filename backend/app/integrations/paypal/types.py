"""Typed views of the PayPal response fields Covenant relies on. Parsers fail loudly
(KeyError/ValueError) when PayPal returns something unexpected; callers treat that as a
definite failure of the call that produced it."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.money import parse_amount


def _parse_time(value: Any) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None


def _link(body: dict[str, Any], *rels: str) -> str | None:
    links = {link.get("rel"): link.get("href") for link in body.get("links", [])}
    for rel in rels:
        if links.get(rel):
            return str(links[rel])
    return None


@dataclass(frozen=True)
class Authorization:
    id: str
    status: str  # CREATED | CAPTURED | DENIED | PARTIALLY_CAPTURED | VOIDED | PENDING
    amount: Decimal
    currency: str
    expiration_time: datetime | None
    custom_id: str | None

    @classmethod
    def parse(cls, body: dict[str, Any]) -> "Authorization":
        return cls(
            id=str(body["id"]),
            status=str(body["status"]),
            amount=parse_amount(body["amount"]["value"]),
            currency=str(body["amount"]["currency_code"]),
            expiration_time=_parse_time(body.get("expiration_time")),
            custom_id=body.get("custom_id"),
        )


@dataclass(frozen=True)
class Order:
    id: str
    status: str  # CREATED | PAYER_ACTION_REQUIRED | APPROVED | COMPLETED | VOIDED ...
    authorization: Authorization | None
    payer_action_url: str | None
    captures: tuple["Capture", ...] = ()

    @classmethod
    def parse(cls, body: dict[str, Any]) -> "Order":
        units = body.get("purchase_units") or []
        payments = (units[0].get("payments") or {}) if units else {}
        authorizations = payments.get("authorizations") or []
        return cls(
            id=str(body["id"]),
            status=str(body["status"]),
            authorization=Authorization.parse(authorizations[0]) if authorizations else None,
            payer_action_url=_link(body, "payer-action", "approve"),
            captures=tuple(Capture.parse(c) for c in payments.get("captures") or []),
        )


@dataclass(frozen=True)
class SetupToken:
    id: str
    status: str  # CREATED | PAYER_ACTION_REQUIRED | APPROVED | VAULTED | TOKENIZED
    approve_url: str | None

    @classmethod
    def parse(cls, body: dict[str, Any]) -> "SetupToken":
        return cls(
            id=str(body["id"]),
            status=str(body.get("status") or "CREATED"),
            approve_url=_link(body, "approve", "payer-action"),
        )


@dataclass(frozen=True)
class PaymentToken:
    id: str
    customer_id: str
    payer_email: str | None

    @classmethod
    def parse(cls, body: dict[str, Any]) -> "PaymentToken":
        paypal = (body.get("payment_source") or {}).get("paypal") or {}
        return cls(
            id=str(body["id"]),
            customer_id=str(body["customer"]["id"]),
            payer_email=paypal.get("email_address"),
        )


@dataclass(frozen=True)
class Capture:
    id: str
    status: str  # COMPLETED | PENDING | DECLINED | FAILED ...
    amount: Decimal
    final_capture: bool

    @classmethod
    def parse(cls, body: dict[str, Any]) -> "Capture":
        return cls(
            id=str(body["id"]),
            status=str(body["status"]),
            amount=parse_amount(body["amount"]["value"]),
            final_capture=bool(body.get("final_capture", False)),
        )


@dataclass(frozen=True)
class PayoutItem:
    item_id: str
    transaction_status: str  # SUCCESS | FAILED | PENDING | UNCLAIMED | RETURNED | ONHOLD ...
    sender_item_id: str | None
    error: str | None

    @classmethod
    def parse(cls, body: dict[str, Any]) -> "PayoutItem":
        errors = body.get("errors") or {}
        error = (errors.get("message") or errors.get("name")) if isinstance(errors, dict) else None
        return cls(
            item_id=str(body["payout_item_id"]),
            transaction_status=str(body.get("transaction_status") or "PENDING"),
            sender_item_id=(body.get("payout_item") or {}).get("sender_item_id"),
            error=error,
        )


@dataclass(frozen=True)
class PayoutBatch:
    batch_id: str
    batch_status: str  # PENDING | PROCESSING | SUCCESS | DENIED | CANCELED
    sender_batch_id: str | None
    items: tuple[PayoutItem, ...]

    @classmethod
    def parse(cls, body: dict[str, Any]) -> "PayoutBatch":
        header = body["batch_header"]
        return cls(
            batch_id=str(header["payout_batch_id"]),
            batch_status=str(header["batch_status"]),
            sender_batch_id=(header.get("sender_batch_header") or {}).get("sender_batch_id"),
            items=tuple(PayoutItem.parse(item) for item in body.get("items") or []),
        )
