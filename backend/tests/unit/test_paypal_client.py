import json
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from app.core.redaction import REDACTED
from app.integrations.paypal import (
    PayPalApiError,
    PayPalClient,
    PayPalConfig,
    PayPalNetworkError,
    PayPalNotConfigured,
)
from app.integrations.paypal.audit import Operation, OperationRecord, operation_request_id
from app.integrations.paypal.http import PayPalHttp

BASE = "https://paypal.test"
CONFIG = PayPalConfig(
    base_url=BASE,
    client_id="client",
    client_secret="secret",
    webhook_id="WH-1",
    timeout_seconds=5,
    currency="USD",
    brand_name="Covenant",
    return_base_url="http://localhost:8000",
    payouts_enabled=True,
)


class MemoryRecorder:
    def __init__(self) -> None:
        self.records: list[OperationRecord] = []

    async def record(self, record: OperationRecord) -> None:
        self.records.append(record)


def authorization_body(status: str = "CREATED", amount: str = "40.00") -> dict[str, Any]:
    return {
        "id": "AUTH-1",
        "status": status,
        "amount": {"currency_code": "USD", "value": amount},
        "expiration_time": "2026-12-02T10:00:00Z",
        "custom_id": "contract-1",
    }


def order_body(status: str, *, with_auth: bool) -> dict[str, Any]:
    payments = {"authorizations": [authorization_body()]} if with_auth else {}
    return {
        "id": "ORDER-1",
        "status": status,
        "purchase_units": [{"reference_id": "C-1042", "payments": payments}],
        "links": [{"rel": "payer-action", "href": "https://sandbox.paypal.test/checkoutnow?t=1"}],
    }


def api_error(status: int, name: str, issue: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"name": name, "message": "m", "debug_id": "dbg-9", "details": [{"issue": issue}]},
    )


@pytest.fixture
def recorder() -> MemoryRecorder:
    return MemoryRecorder()


@pytest.fixture
async def paypal(recorder: MemoryRecorder) -> AsyncIterator[tuple[PayPalClient, respx.MockRouter]]:
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.post("/v1/oauth2/token").respond(
            json={"access_token": "token-1", "expires_in": 32400}
        )
        client = PayPalClient(CONFIG, recorder=recorder)
        yield client, router
        await client.aclose()


def op(kind: str = "create_order") -> Operation:
    return Operation(kind=kind, request_id=f"cov-c1-{kind}-1", contract_id="c1")  # type: ignore[arg-type]


async def test_vaulted_order_is_authorized_immediately(
    paypal: tuple[PayPalClient, respx.MockRouter], recorder: MemoryRecorder
) -> None:
    client, router = paypal
    route = router.post("/v2/checkout/orders").respond(
        201,
        json=order_body("COMPLETED", with_auth=True),
        headers={"PayPal-Debug-Id": "dbg-1"},
    )
    order = await client.create_authorize_order(
        operation=op(),
        amount=Decimal("40.00"),
        reference_id="C-1042",
        custom_id="contract-1",
        invoice_id="C-1042",
        description="x" * 200,
        vault_id="VAULT-SECRET",
    )
    assert order.authorization is not None
    assert order.authorization.id == "AUTH-1"
    assert order.authorization.amount == Decimal("40.00")

    request = route.calls.last.request
    assert request.headers["PayPal-Request-Id"] == "cov-c1-create_order-1"
    assert request.headers["Prefer"] == "return=representation"
    assert request.headers["Authorization"] == "Bearer token-1"
    sent = json.loads(request.content)
    assert sent["intent"] == "AUTHORIZE"
    unit = sent["purchase_units"][0]
    assert unit["amount"] == {"currency_code": "USD", "value": "40.00"}
    assert unit["custom_id"] == "contract-1"
    assert len(unit["description"]) == 127
    assert sent["payment_source"]["paypal"] == {"vault_id": "VAULT-SECRET"}

    [record] = recorder.records
    assert record.operation.kind == "create_order"
    assert record.response_status == 201
    assert record.paypal_debug_id == "dbg-1"
    assert record.request_body["payment_source"]["paypal"]["vault_id"] == REDACTED


async def test_approve_each_order_returns_payer_action_link(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, router = paypal
    route = router.post("/v2/checkout/orders").respond(
        200, json=order_body("PAYER_ACTION_REQUIRED", with_auth=False)
    )
    order = await client.create_authorize_order(
        operation=op(),
        amount=Decimal("25.00"),
        reference_id="C-1",
        custom_id="c1",
        invoice_id="C-1",
        description="d",
        return_url="http://localhost:8000/r",
        cancel_url="http://localhost:8000/c",
    )
    assert order.authorization is None
    assert order.payer_action_url == "https://sandbox.paypal.test/checkoutnow?t=1"
    context = json.loads(route.calls.last.request.content)["payment_source"]["paypal"]
    assert context["experience_context"]["return_url"] == "http://localhost:8000/r"


async def test_order_without_vault_requires_return_urls(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, _ = paypal
    with pytest.raises(ValueError, match="return_url"):
        await client.create_authorize_order(
            operation=op(),
            amount=Decimal("1.00"),
            reference_id="r",
            custom_id="c",
            invoice_id="i",
            description="d",
        )


async def test_token_is_cached_and_refreshed_before_expiry(recorder: MemoryRecorder) -> None:
    now = [1000.0]
    with respx.mock(base_url=BASE) as router:
        token_route = router.post("/v1/oauth2/token").respond(
            json={"access_token": "t", "expires_in": 120}
        )
        router.get("/v2/payments/authorizations/AUTH-1").respond(json=authorization_body())
        http = PayPalHttp(CONFIG, recorder=recorder, clock=lambda: now[0])
        client = PayPalClient(CONFIG)
        client.transport = http
        await client.get_authorization("AUTH-1")
        await client.get_authorization("AUTH-1")
        assert token_route.call_count == 1
        now[0] += 61  # inside the 60 s refresh margin of a 120 s token
        await client.get_authorization("AUTH-1")
        assert token_route.call_count == 2
        token_request = token_route.calls.last.request
        assert token_request.headers["Authorization"].startswith("Basic ")
        assert token_request.content == b"grant_type=client_credentials"
        await client.aclose()


async def test_expired_token_is_refreshed_once_on_401(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, router = paypal
    route = router.get("/v2/payments/authorizations/AUTH-1").mock(
        side_effect=[httpx.Response(401, json={}), httpx.Response(200, json=authorization_body())]
    )
    authorization = await client.get_authorization("AUTH-1")
    assert authorization.status == "CREATED"
    assert route.call_count == 2


async def test_capture_sends_final_partial_amount(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, router = paypal
    route = router.post("/v2/payments/authorizations/AUTH-1/capture").respond(
        201,
        json={
            "id": "CAP-1",
            "status": "COMPLETED",
            "amount": {"currency_code": "USD", "value": "24.00"},
            "final_capture": True,
        },
    )
    capture = await client.capture_authorization(
        "AUTH-1",
        operation=op("capture"),
        amount=Decimal("24.00"),
        invoice_id="C-1042",
        note_to_payer="Covenant C-1042",
    )
    assert capture.id == "CAP-1"
    assert capture.amount == Decimal("24.00")
    assert json.loads(route.calls.last.request.content) == {
        "amount": {"currency_code": "USD", "value": "24.00"},
        "final_capture": True,
        "invoice_id": "C-1042",
        "note_to_payer": "Covenant C-1042",
    }


async def test_capture_of_zero_is_refused(paypal: tuple[PayPalClient, respx.MockRouter]) -> None:
    client, _ = paypal
    with pytest.raises(ValueError, match="void instead"):
        await client.capture_authorization(
            "AUTH-1", operation=op("capture"), amount=Decimal("0"), invoice_id="i", note_to_payer=""
        )


async def test_void_returns_representation(paypal: tuple[PayPalClient, respx.MockRouter]) -> None:
    client, router = paypal
    router.post("/v2/payments/authorizations/AUTH-1/void").respond(
        200, json=authorization_body("VOIDED")
    )
    assert (await client.void_authorization("AUTH-1", operation=op("void"))).status == "VOIDED"


async def test_void_204_reads_authorization(paypal: tuple[PayPalClient, respx.MockRouter]) -> None:
    client, router = paypal
    router.post("/v2/payments/authorizations/AUTH-1/void").respond(204)
    router.get("/v2/payments/authorizations/AUTH-1").respond(json=authorization_body("VOIDED"))
    assert (await client.void_authorization("AUTH-1", operation=op("void"))).status == "VOIDED"


async def test_void_of_already_voided_authorization_is_success(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, router = paypal
    router.post("/v2/payments/authorizations/AUTH-1/void").mock(
        return_value=api_error(422, "UNPROCESSABLE_ENTITY", "SOMETHING_NEW")
    )
    router.get("/v2/payments/authorizations/AUTH-1").respond(json=authorization_body("VOIDED"))
    assert (await client.void_authorization("AUTH-1", operation=op("void"))).status == "VOIDED"


async def test_void_of_captured_authorization_raises(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, router = paypal
    router.post("/v2/payments/authorizations/AUTH-1/void").mock(
        return_value=api_error(422, "UNPROCESSABLE_ENTITY", "PREVIOUSLY_CAPTURED")
    )
    router.get("/v2/payments/authorizations/AUTH-1").respond(json=authorization_body("CAPTURED"))
    with pytest.raises(PayPalApiError) as excinfo:
        await client.void_authorization("AUTH-1", operation=op("void"))
    assert excinfo.value.has_issue("PREVIOUSLY_CAPTURED")
    assert not excinfo.value.retryable


async def test_reauthorize_returns_new_authorization(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, router = paypal
    body = {**authorization_body(), "id": "AUTH-2"}
    route = router.post("/v2/payments/authorizations/AUTH-1/reauthorize").respond(201, json=body)
    renewed = await client.reauthorize_authorization(
        "AUTH-1", operation=op("reauthorize"), amount=Decimal("40.00")
    )
    assert renewed.id == "AUTH-2"
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"amount": {"currency_code": "USD", "value": "40.00"}}


@pytest.mark.parametrize(
    ("status", "retryable"), [(400, False), (409, True), (422, False), (429, True), (503, True)]
)
async def test_error_classification(
    paypal: tuple[PayPalClient, respx.MockRouter],
    recorder: MemoryRecorder,
    status: int,
    retryable: bool,
) -> None:
    client, router = paypal
    router.post("/v2/payments/authorizations/AUTH-1/capture").mock(
        return_value=api_error(status, "ERR", "ISSUE_X")
    )
    with pytest.raises(PayPalApiError) as excinfo:
        await client.capture_authorization(
            "AUTH-1",
            operation=op("capture"),
            amount=Decimal("1.00"),
            invoice_id="i",
            note_to_payer="",
        )
    error = excinfo.value
    assert error.retryable is retryable
    assert error.issues == ("ISSUE_X",)
    assert error.debug_id == "dbg-9"
    assert recorder.records[-1].response_status == status


async def test_timeout_is_retryable_with_unknown_outcome(
    paypal: tuple[PayPalClient, respx.MockRouter], recorder: MemoryRecorder
) -> None:
    client, router = paypal
    router.post("/v2/payments/authorizations/AUTH-1/void").mock(
        side_effect=httpx.ReadTimeout("slow")
    )
    with pytest.raises(PayPalNetworkError) as excinfo:
        await client.void_authorization("AUTH-1", operation=op("void"))
    assert excinfo.value.retryable
    assert excinfo.value.outcome_unknown
    assert recorder.records[-1].response_status is None


async def test_connect_error_has_known_outcome(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, router = paypal
    router.post("/v2/payments/authorizations/AUTH-1/void").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(PayPalNetworkError) as excinfo:
        await client.void_authorization("AUTH-1", operation=op("void"))
    assert not excinfo.value.outcome_unknown


async def test_payout_uses_sender_batch_id_as_request_id(
    paypal: tuple[PayPalClient, respx.MockRouter], recorder: MemoryRecorder
) -> None:
    client, router = paypal
    route = router.post("/v1/payments/payouts").respond(
        201,
        json={
            "batch_header": {
                "payout_batch_id": "BATCH-1",
                "batch_status": "PENDING",
                "sender_batch_header": {"sender_batch_id": "cov-payout-p1"},
            }
        },
    )
    batch = await client.create_payout(
        payout_id="p1",
        contract_id="c1",
        receiver_email="kabir@example.com",
        amount=Decimal("38.00"),
        sender_item_id="C-1042",
        note="Payment for C-1042",
        email_subject="You were paid",
    )
    assert batch.batch_id == "BATCH-1"
    assert batch.sender_batch_id == "cov-payout-p1"
    request = route.calls.last.request
    assert request.headers["PayPal-Request-Id"] == "cov-payout-p1"
    sent = json.loads(request.content)
    assert sent["sender_batch_header"]["sender_batch_id"] == "cov-payout-p1"
    assert sent["items"] == [
        {
            "recipient_type": "EMAIL",
            "receiver": "kabir@example.com",
            "amount": {"value": "38.00", "currency": "USD"},
            "sender_item_id": "C-1042",
            "note": "Payment for C-1042",
        }
    ]
    assert recorder.records[-1].operation.kind == "payout"


async def test_payout_batch_items_are_parsed(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, router = paypal
    router.get("/v1/payments/payouts/BATCH-1").respond(
        json={
            "batch_header": {"payout_batch_id": "BATCH-1", "batch_status": "SUCCESS"},
            "items": [
                {
                    "payout_item_id": "ITEM-1",
                    "transaction_status": "UNCLAIMED",
                    "payout_item": {"sender_item_id": "C-1042"},
                    "errors": {"name": "RECEIVER_UNREGISTERED", "message": "No PayPal account"},
                }
            ],
        }
    )
    batch = await client.get_payout_batch("BATCH-1")
    [item] = batch.items
    assert item.transaction_status == "UNCLAIMED"
    assert item.sender_item_id == "C-1042"
    assert item.error == "No PayPal account"


WEBHOOK_HEADERS = {
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "PAYPAL-TRANSMISSION-ID": "tid",
    "PAYPAL-TRANSMISSION-SIG": "sig",
    "PAYPAL-TRANSMISSION-TIME": "2026-11-03T10:00:00Z",
}


@pytest.mark.parametrize(("verification", "expected"), [("SUCCESS", True), ("FAILURE", False)])
async def test_webhook_signature_verification(
    paypal: tuple[PayPalClient, respx.MockRouter], verification: str, expected: bool
) -> None:
    client, router = paypal
    route = router.post("/v1/notifications/verify-webhook-signature").respond(
        json={"verification_status": verification}
    )
    event = {"id": "WH-EVT-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"}
    assert await client.verify_webhook_signature(WEBHOOK_HEADERS, event) is expected
    sent = json.loads(route.calls.last.request.content)
    assert sent["webhook_id"] == "WH-1"
    assert sent["transmission_id"] == "tid"
    assert sent["webhook_event"] == event
    assert "PayPal-Request-Id" not in route.calls.last.request.headers


async def test_webhook_missing_headers_fail_without_calling_paypal(
    paypal: tuple[PayPalClient, respx.MockRouter],
) -> None:
    client, router = paypal
    route = router.post("/v1/notifications/verify-webhook-signature")
    headers = {k: v for k, v in WEBHOOK_HEADERS.items() if k != "PAYPAL-TRANSMISSION-SIG"}
    assert await client.verify_webhook_signature(headers, {"id": "x"}) is False
    assert not route.called


async def test_unconfigured_client_refuses_calls() -> None:
    client = PayPalClient(PayPalConfig(**{**CONFIG.__dict__, "client_id": "", "client_secret": ""}))
    with pytest.raises(PayPalNotConfigured):
        await client.get_authorization("AUTH-1")
    await client.aclose()


def test_operation_request_ids_are_deterministic() -> None:
    assert operation_request_id("c1", "capture", 1) == "cov-c1-capture-1"
    assert operation_request_id("c1", "capture", 2) == "cov-c1-capture-2"
