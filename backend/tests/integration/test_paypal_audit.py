import pytest
from sqlalchemy import select

from app.db.engine import Database
from app.integrations.paypal.audit import Operation, OperationRecord
from app.models import PayPalOperation
from app.services.paypal_audit import SqlOperationRecorder

pytestmark = pytest.mark.usefixtures("clean_tables")


def record(status: int | None, debug_id: str | None) -> OperationRecord:
    return OperationRecord(
        operation=Operation(kind="capture", request_id="cov-c1-capture-1", contract_id=None),
        http_method="POST",
        path="/v2/payments/authorizations/AUTH-1/capture",
        request_body={"amount": {"currency_code": "USD", "value": "24.00"}},
        response_status=status,
        response_body={"id": "CAP-1"} if status else {"error": "ReadTimeout"},
        paypal_debug_id=debug_id,
    )


async def test_retry_with_same_request_id_updates_one_row(database: Database) -> None:
    recorder = SqlOperationRecorder(database)
    await recorder.record(record(None, None))
    await recorder.record(record(201, "dbg-2"))

    async with database.session() as session:
        rows = (await session.execute(select(PayPalOperation))).scalars().all()
    [row] = rows
    assert row.request_id == "cov-c1-capture-1"
    assert row.kind == "capture"
    assert row.attempts == 2
    assert row.response_status == 201
    assert row.paypal_debug_id == "dbg-2"
    assert row.response_body == {"id": "CAP-1"}
    assert row.request_body == {"amount": {"currency_code": "USD", "value": "24.00"}}
