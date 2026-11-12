from sqlalchemy.dialects.mysql import insert

from app.core.ids import uuid7
from app.db.base import utcnow
from app.db.engine import Database
from app.integrations.paypal.audit import OperationRecord
from app.models import PayPalOperation


class SqlOperationRecorder:
    """Writes PayPal audit rows in their own transaction, so the trail survives even when the
    caller's business transaction rolls back."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def record(self, record: OperationRecord) -> None:
        now = utcnow()
        values = {
            "id": uuid7(),
            "contract_id": record.operation.contract_id,
            "kind": record.operation.kind,
            "request_id": record.operation.request_id,
            "http_method": record.http_method,
            "path": record.path[:255],
            "request_body": record.request_body,
            "response_status": record.response_status,
            "response_body": record.response_body,
            "paypal_debug_id": record.paypal_debug_id,
            "attempts": 1,
            "created_at": now,
            "updated_at": now,
        }
        statement = insert(PayPalOperation).values(**values)
        statement = statement.on_duplicate_key_update(
            response_status=statement.inserted.response_status,
            response_body=statement.inserted.response_body,
            paypal_debug_id=statement.inserted.paypal_debug_id,
            attempts=PayPalOperation.attempts + 1,
            updated_at=statement.inserted.updated_at,
        )
        async with self._database.session() as session, session.begin():
            await session.execute(statement)
