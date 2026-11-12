"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

from app.models.contract import Approval, Contract, ContractEvent
from app.models.escrow import Escrow, IdempotencyKey, Payout
from app.models.funding import PayPalFundingAccount, PayPalVaultSession
from app.models.identity import Membership, Organization, RefreshToken, User
from app.models.ledger import LedgerEntry
from app.models.mandate import Mandate
from app.models.outbox import OutboxJob
from app.models.paypal_operation import PayPalOperation
from app.models.records import (
    AgentConversation,
    AgentMessage,
    ApiKey,
    Appeal,
    Delivery,
    Notification,
    StoredFile,
    Verdict,
)
from app.models.webhook import ReconciliationRun, WebhookEvent
from app.models.worker import Worker, WorkerVerification

__all__ = [
    "AgentConversation",
    "AgentMessage",
    "ApiKey",
    "Appeal",
    "Approval",
    "Contract",
    "ContractEvent",
    "Delivery",
    "Escrow",
    "IdempotencyKey",
    "LedgerEntry",
    "Mandate",
    "Membership",
    "Notification",
    "Organization",
    "OutboxJob",
    "PayPalFundingAccount",
    "PayPalOperation",
    "PayPalVaultSession",
    "Payout",
    "ReconciliationRun",
    "RefreshToken",
    "StoredFile",
    "User",
    "Verdict",
    "WebhookEvent",
    "Worker",
    "WorkerVerification",
]
