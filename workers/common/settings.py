"""Environment for every demo worker. Reads `workers/.env`."""

from pathlib import Path

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WORKERS_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_WORKERS_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    worker_host: str = "127.0.0.1"
    lipi_port: int = 9101
    tally_port: int = 9102
    quickwordz_port: int = 9103
    lipi_public_url: str = "http://127.0.0.1:9101"
    tally_public_url: str = "http://127.0.0.1:9102"
    quickwordz_public_url: str = "http://127.0.0.1:9103"
    lipi_auth_token: str = "dev-lipi-token-7c21b9"  # noqa: S105
    tally_auth_token: str = "dev-tally-token-4e88d0"  # noqa: S105
    quickwordz_auth_token: str = "dev-quickwordz-token-a19f3c"  # noqa: S105
    tally_fault_rate: float = 0.2
    quickwordz_adversarial: bool = True
    ai_provider: str = ""
    ai_api_key: SecretStr = SecretStr("")
    ai_base_url: str = ""
    ai_model: str = ""
    ai_fast: str = ""
    ai_timeout_seconds: float = 60

    @model_validator(mode="before")
    @classmethod
    def _strip_inline_comments(cls, data: object) -> object:
        """workers/.env.example ships comments on the same line as values."""
        if isinstance(data, dict):
            return {
                key: value.split(" #", 1)[0].strip() if isinstance(value, str) else value
                for key, value in data.items()
            }
        return data
