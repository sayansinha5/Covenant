from decimal import Decimal

import pytest

from app.core.config import ConfigurationError, load_settings
from tests.conftest import BASE_SETTINGS, make_settings


def test_comma_lists_are_split() -> None:
    settings = make_settings(cors_allowed_origins="http://a.test, http://b.test")
    assert settings.cors_allowed_origins == ["http://a.test", "http://b.test"]
    assert settings.allowed_agent_hosts == ["lipi", "tally"]


def test_money_values_are_decimals() -> None:
    settings = make_settings()
    assert settings.default_per_task_cap == Decimal("60.00")
    assert settings.platform_fee_rate == Decimal("0.05")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_default_jwt_secret_refused_outside_development(env: str) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        make_settings(app_env=env)


def test_wildcard_cors_refused() -> None:
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        make_settings(cors_allowed_origins="*")


def test_mandate_defaults_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="approval threshold"):
        make_settings(default_approval_threshold="70.00")


def test_comment_parsed_as_value_is_refused() -> None:
    with pytest.raises(ValueError, match="PAYPAL_CLIENT_ID is set to a comment"):
        make_settings(paypal_client_id="# from your sandbox REST app")


def test_external_credentials_report_not_configured() -> None:
    settings = make_settings()
    assert not settings.paypal_configured
    assert not settings.ai_configured
    assert not settings.langsmith_enabled


def test_ai_configured_needs_provider_model_and_key() -> None:
    assert make_settings(ai_provider="openai", ai_model="m", ai_api_key="k").ai_configured
    assert not make_settings(ai_provider="openai", ai_model="m").ai_configured
    assert make_settings(ai_provider="ollama", ai_model="m").ai_configured


def test_environment_values_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in BASE_SETTINGS.items():
        monkeypatch.setenv(key.upper(), str(value))
    monkeypatch.setenv("ALLOWED_AGENT_HOSTS", "lipi,tally,quickwordz,host.docker.internal")
    settings = load_settings()
    assert settings.allowed_agent_hosts[-1] == "host.docker.internal"
    assert settings.db_password.get_secret_value() == "pw"


def test_missing_values_are_listed_readably(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", "not-a-number")
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    assert message.startswith("Invalid or missing configuration values:")
    assert "  - DB_PASSWORD: Field required" in message
    assert "  - DB_POOL_SIZE:" in message
