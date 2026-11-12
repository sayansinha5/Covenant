from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class PayPalConfig:
    base_url: str
    client_id: str
    client_secret: str
    webhook_id: str
    timeout_seconds: float
    currency: str
    brand_name: str
    return_base_url: str
    payouts_enabled: bool

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @classmethod
    def from_settings(cls, settings: Settings) -> "PayPalConfig":
        return cls(
            base_url=settings.paypal_base_url.rstrip("/"),
            client_id=settings.paypal_client_id,
            client_secret=settings.paypal_client_secret.get_secret_value(),
            webhook_id=settings.paypal_webhook_id,
            timeout_seconds=settings.paypal_http_timeout_seconds,
            currency=settings.currency,
            brand_name=settings.app_name,
            return_base_url=settings.paypal_return_base_url.rstrip("/"),
            payouts_enabled=settings.paypal_payouts_enabled,
        )
