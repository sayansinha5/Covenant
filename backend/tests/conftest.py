from typing import Any

import pytest
from hypothesis import settings as hypothesis_settings
from hypothesis.database import DirectoryBasedExampleDatabase

from app.core.config import DEFAULT_DEV_JWT_SECRET, Settings

# Keep Hypothesis' example database out of the source tree.
hypothesis_settings.register_profile(
    "covenant",
    database=DirectoryBasedExampleDatabase("/tmp/hypothesis"),  # noqa: S108
)
hypothesis_settings.load_profile("covenant")

BASE_SETTINGS: dict[str, Any] = {
    "app_env": "test",
    "frontend_origin": "http://localhost:5173",
    "cors_allowed_origins": "http://localhost:5173",
    "db_host": "mysql",
    "db_name": "covenant",
    "db_test_name": "covenant_test",
    "db_user": "covenant_app",
    "db_password": "pw",
    "db_migrator_user": "covenant_migrator",
    "db_migrator_password": "pw",
    "jwt_secret": DEFAULT_DEV_JWT_SECRET,
    "jwt_issuer": "covenant-local",
    "jwt_audience": "covenant-web",
    "access_token_ttl_minutes": 15,
    "refresh_token_ttl_days": 7,
    "login_max_attempts": 5,
    "login_lockout_minutes": 15,
    "seed_admin_email": "admin@covenant.local",
    "seed_admin_password": "ChangeMe-Admin-2026",
    "paypal_base_url": "https://api-m.sandbox.paypal.com",
    "paypal_return_base_url": "http://localhost:8000",
    "platform_fee_rate": "0.05",
    "default_monthly_budget": "300.00",
    "default_per_task_cap": "60.00",
    "default_approval_threshold": "40.00",
    "approval_expiry_hours": 24,
    "appeal_window_minutes": 60,
    "agent_accept_timeout_minutes": 10,
    "agent_default_deadline_minutes": 30,
    "human_accept_timeout_hours": 24,
    "human_default_deadline_hours": 72,
    "auth_honor_period_days": 3,
    "arbiter_item_pass_score": 7.0,
    "arbiter_pass_band_min": 0.9,
    "arbiter_partial_band_min": 0.5,
    "arbiter_border_margin": 0.05,
    "arbiter_low_confidence": 0.6,
    "arbiter_manipulation_threshold": 0.8,
    "arbiter_batch_size": 10,
    "max_delivery_bytes": 1048576,
    "allowed_agent_hosts": "lipi,tally",
    "storage_dir": "/tmp/storage",  # noqa: S108
    "max_upload_mb": 5,
    "rate_limit_auth": "10/minute",
    "rate_limit_money": "30/minute",
    "rate_limit_assistant": "20/minute",
}


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see the real credentials from the environment."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def make_settings(**overrides: Any) -> Settings:
    return Settings(**{**BASE_SETTINGS, **overrides})


@pytest.fixture
def settings() -> Settings:
    return make_settings()
