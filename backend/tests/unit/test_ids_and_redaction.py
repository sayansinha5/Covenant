import time
import uuid

from app.core.ids import uuid7
from app.core.redaction import REDACTED, redact


def test_uuid7_version_variant_and_order() -> None:
    first = uuid7()
    time.sleep(0.002)
    second = uuid7()
    parsed = uuid.UUID(first)
    assert parsed.version == 7
    assert parsed.variant == uuid.RFC_4122
    assert len(first) == 36
    assert first < second


def test_redact_hides_secrets_but_keeps_paypal_ids() -> None:
    payload = {
        "Authorization": "Bearer abc",
        "client_secret": "s",
        "payment_source": {"paypal": {"vault_id": "8kk8451t"}},
        "access_token": "tok",
        "setup_token": "st",
        "purchase_units": [{"payments": {"authorizations": [{"id": "AUTH-1"}]}}],
        "amount": {"value": "40.00"},
    }
    result = redact(payload)
    assert result["Authorization"] == REDACTED
    assert result["client_secret"] == REDACTED
    assert result["payment_source"]["paypal"]["vault_id"] == REDACTED
    assert result["access_token"] == REDACTED
    assert result["setup_token"] == REDACTED
    assert result["purchase_units"][0]["payments"]["authorizations"][0]["id"] == "AUTH-1"
    assert result["amount"] == {"value": "40.00"}
    assert payload["client_secret"] == "s"  # input untouched
