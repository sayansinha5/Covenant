import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.integrations.elastic.query import elasticsearch_endpoint

DEFAULT_DEV_JWT_SECRET = "dev-only-covenant-jwt-secret-change-me-0f8e3a71c94b2d56e1a7"  # noqa: S105
RELAXED_SECRET_ENVS = frozenset({"development", "test"})
PAYPAL_SANDBOX_API_HOSTS = frozenset({"api-m.sandbox.paypal.com", "api.sandbox.paypal.com"})
_ACCOUNT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
CommaList = Annotated[list[str], NoDecode]


class ConfigurationError(RuntimeError):
    """Raised at startup when the environment is missing or has invalid values."""


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    """Every configurable value of the backend. The process environment wins, then
    `backend/.env`, then the repo-root `.env`."""

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(_BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # ── App ─────────────────────────────────────────────
    app_env: str = "development"
    app_name: str = "Covenant"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_origin: str
    cors_allowed_origins: CommaList
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    runner_embedded: bool = False
    runner_poll_seconds: float = Field(default=1, gt=0)
    runner_batch_size: int = Field(default=5, gt=0, le=100)
    # Longer than the slowest job (an Arbiter run); a job held past it is handed to another runner.
    runner_lease_seconds: int = Field(default=600, ge=60)

    # ── Database ───────────────────────────────────────
    db_host: str
    db_port: int = 3306
    db_name: str
    db_test_name: str
    db_user: str
    db_password: SecretStr
    db_migrator_user: str
    db_migrator_password: SecretStr
    db_pool_size: int = Field(default=10, ge=1, le=100)

    # ── Auth ───────────────────────────────────────────
    jwt_secret: SecretStr
    jwt_issuer: str
    jwt_audience: str
    access_token_ttl_minutes: int = Field(gt=0)
    refresh_token_ttl_days: int = Field(gt=0)
    login_max_attempts: int = Field(gt=0)
    login_lockout_minutes: int = Field(gt=0)
    seed_admin_email: str
    seed_admin_password: SecretStr

    # ── PayPal ─────────────────────────────────────────
    paypal_env: Literal["sandbox"] = "sandbox"
    paypal_base_url: str
    paypal_client_id: str = ""
    paypal_client_secret: SecretStr = SecretStr("")
    paypal_webhook_id: str = ""
    paypal_funding_mode: Literal["vault", "approve_each"] = "vault"
    paypal_payouts_enabled: bool = True
    paypal_return_base_url: str
    paypal_http_timeout_seconds: float = Field(default=15, gt=0)

    # ── Money and policy defaults ──────────────────────
    currency: Literal["USD"] = "USD"
    platform_fee_rate: Decimal = Field(ge=0, lt=1)
    default_monthly_budget: Money
    default_per_task_cap: Money
    default_approval_threshold: Money
    approval_expiry_hours: float = Field(gt=0)
    appeal_window_minutes: float = Field(gt=0)
    agent_accept_timeout_minutes: float = Field(gt=0)
    agent_default_deadline_minutes: float = Field(gt=0)
    human_accept_timeout_hours: float = Field(gt=0)
    human_default_deadline_hours: float = Field(gt=0)
    auth_honor_period_days: int = Field(gt=0)

    # ── AI provider ────────────────────────────────────
    ai_provider: str = ""
    ai_api_key: SecretStr = SecretStr("")
    ai_base_url: str = ""
    ai_api_version: str = ""
    ai_model: str = ""
    ai_fast: str = ""
    ai_medium: str = ""
    ai_super: str = ""
    ai_reasoning: str = ""
    ai_timeout_seconds: float = Field(default=60, gt=0)
    ai_max_retries: int = Field(default=2, ge=0)
    second_opinion_provider: str = ""
    second_opinion_model: str = ""
    second_opinion_api_key: SecretStr = SecretStr("")
    second_opinion_base_url: str = ""

    # ── Arbiter tuning ─────────────────────────────────
    arbiter_item_pass_score: float = Field(ge=0, le=10)
    arbiter_pass_band_min: float = Field(gt=0, le=1)
    arbiter_partial_band_min: float = Field(gt=0, le=1)
    arbiter_border_margin: float = Field(ge=0, lt=1)
    arbiter_low_confidence: float = Field(ge=0, le=1)
    arbiter_manipulation_threshold: float = Field(ge=0, le=1)
    arbiter_batch_size: int = Field(gt=0)
    max_delivery_bytes: int = Field(gt=0)

    # ── LangSmith ──────────────────────────────────────
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr = SecretStr("")
    langsmith_project: str = "covenant-local"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # ── Catalog, search, and the agent fleet ───────
    channel3_api_key: SecretStr = SecretStr("")
    channel3_base_url: str = "https://api.trychannel3.com"
    astropods_api_token: SecretStr = SecretStr("")
    astropods_account: str = ""
    astropods_base_url: str = "https://astropods.com/api/v1"
    elasticsearch_url: str = ""
    elastic_api_key: SecretStr = SecretStr("")
    elastic_cloud_id: str = ""

    # ── Workers and uploads ────────────────────────────
    allowed_agent_hosts: CommaList
    # Dev defaults match workers/.env.example. Change them in both files together.
    lipi_auth_token: str = "dev-lipi-token-7c21b9"  # noqa: S105
    tally_auth_token: str = "dev-tally-token-4e88d0"  # noqa: S105
    quickwordz_auth_token: str = "dev-quickwordz-token-a19f3c"  # noqa: S105
    agent_http_timeout_seconds: float = Field(default=5, gt=0)
    storage_dir: str
    max_upload_mb: int = Field(gt=0)

    # ── Rate limits ────────────────────────────────────
    rate_limit_auth: str
    rate_limit_money: str
    rate_limit_assistant: str

    @model_validator(mode="before")
    @classmethod
    def _reject_comment_values(cls, data: object) -> object:
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and value.lstrip().startswith("#"):
                    raise ValueError(
                        f"{str(key).upper()} is set to a comment ({value.strip()[:40]!r}); "
                        "put the comment on its own line"
                    )
        return data

    @field_validator("cors_allowed_origins", "allowed_agent_hosts", mode="before")
    @classmethod
    def _split_comma_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> "Settings":
        if self.app_env not in RELAXED_SECRET_ENVS and (
            self.jwt_secret.get_secret_value() == DEFAULT_DEV_JWT_SECRET
        ):
            raise ValueError(
                f"JWT_SECRET still has the shipped development default; "
                f"set a new secret when APP_ENV={self.app_env}"
            )
        if urlparse(self.paypal_base_url).hostname not in PAYPAL_SANDBOX_API_HOSTS:
            raise ValueError(
                "PAYPAL_BASE_URL must be PayPal's sandbox REST API, "
                "https://api-m.sandbox.paypal.com (not the sandbox website)"
            )
        if "*" in self.cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must list exact origins, not '*'")
        if self.arbiter_partial_band_min > self.arbiter_pass_band_min:
            raise ValueError("ARBITER_PARTIAL_BAND_MIN must not exceed ARBITER_PASS_BAND_MIN")
        _require_http_url(self.channel3_base_url, "CHANNEL3_BASE_URL", https=True)
        _require_http_url(self.astropods_base_url, "ASTROPODS_BASE_URL", https=True)
        if self.astropods_account and not _ACCOUNT.fullmatch(self.astropods_account):
            raise ValueError(
                "ASTROPODS_ACCOUNT may only contain letters, numbers, dots, underscores and hyphens"
            )
        if self.elasticsearch_url.strip():
            _require_http_url(self.elasticsearch_url, "ELASTICSEARCH_URL", https=False)
        if self.elastic_cloud_id.strip() or self.elasticsearch_url.strip():
            elasticsearch_endpoint(self.elasticsearch_url, self.elastic_cloud_id)
        if not (
            self.default_approval_threshold
            <= self.default_per_task_cap
            <= self.default_monthly_budget
        ):
            raise ValueError(
                "Mandate defaults must satisfy approval threshold <= per-task cap <= monthly budget"
            )
        return self

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret.get_secret_value())

    @property
    def ai_configured(self) -> bool:
        if not self.ai_provider or not (self.ai_model or self.ai_medium):
            return False
        return self.ai_provider == "ollama" or bool(self.ai_api_key.get_secret_value())

    @property
    def langsmith_enabled(self) -> bool:
        return self.langsmith_tracing and bool(self.langsmith_api_key.get_secret_value())

    @property
    def channel3_configured(self) -> bool:
        return bool(self.channel3_api_key.get_secret_value())

    @property
    def astropods_configured(self) -> bool:
        return bool(self.astropods_api_token.get_secret_value() and self.astropods_account.strip())

    @property
    def elastic_configured(self) -> bool:
        return bool(self.elasticsearch_url.strip() or self.elastic_cloud_id.strip())


def _require_http_url(value: str, name: str, *, https: bool) -> None:
    parsed = urlparse(value.strip())
    schemes = ("https",) if https else ("http", "https")
    if parsed.scheme not in schemes or not parsed.hostname or parsed.username or parsed.password:
        kind = "an https URL" if https else "an http or https URL"
        raise ValueError(f"{name} must be {kind} without a username or password")


def format_validation_error(exc: ValidationError) -> str:
    lines = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]).upper() or "SETTINGS"
        lines.append(f"  - {field}: {error['msg']}")
    return "Invalid or missing configuration values:\n" + "\n".join(lines)


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigurationError(format_validation_error(exc)) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
