"""Provider-agnostic chat models by tier, built with LangChain's `init_chat_model`."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.core.config import Settings


class Tier(StrEnum):
    FAST = "fast"
    MEDIUM = "medium"
    SUPER = "super"
    REASONING = "reasoning"


# None keeps the provider's default (reasoning models often reject a temperature).
DEFAULT_TEMPERATURE: dict[Tier, float | None] = {
    Tier.FAST: 0.0,
    Tier.MEDIUM: 0.2,
    Tier.SUPER: 0.0,
    Tier.REASONING: None,
}

PROVIDER_PACKAGES = {
    "openai": "langchain-openai",
    "azure_openai": "langchain-openai",
    "anthropic": "langchain-anthropic",
    "google_genai": "langchain-google-genai",
    "mistralai": "langchain-mistralai",
    "groq": "langchain-groq",
    "ollama": "langchain-ollama",
}
KEYLESS_PROVIDERS = frozenset({"ollama"})


class AINotConfigured(RuntimeError):
    """The AI provider, model or its LangChain package is missing; the message names the fix."""


@dataclass(frozen=True, slots=True)
class ModelChoice:
    provider: str
    model: str
    api_key: str
    base_url: str
    api_version: str = ""


def tier_model(settings: Settings, tier: Tier) -> str:
    return str(getattr(settings, f"ai_{tier.value}")) or settings.ai_model


def choose(settings: Settings, tier: Tier) -> ModelChoice:
    choice = ModelChoice(
        provider=settings.ai_provider,
        model=tier_model(settings, tier),
        api_key=settings.ai_api_key.get_secret_value(),
        base_url=settings.ai_base_url,
        api_version=settings.ai_api_version,
    )
    _require(choice, f"AI_{tier.value.upper()} or AI_MODEL", "AI_PROVIDER", "AI_API_KEY")
    return choice


def choose_second_opinion(settings: Settings) -> ModelChoice:
    """A different model family when SECOND_OPINION_* is set, else the reasoning tier."""
    if not settings.second_opinion_provider:
        return choose(settings, Tier.REASONING)
    choice = ModelChoice(
        provider=settings.second_opinion_provider,
        model=settings.second_opinion_model,
        api_key=settings.second_opinion_api_key.get_secret_value(),
        base_url=settings.second_opinion_base_url,
    )
    _require(choice, "SECOND_OPINION_MODEL", "SECOND_OPINION_PROVIDER", "SECOND_OPINION_API_KEY")
    return choice


def get_chat_model(
    settings: Settings, tier: Tier, *, temperature: float | None = None
) -> BaseChatModel:
    """The chat model for a tier. `temperature` overrides the tier default."""
    return build(settings, choose(settings, tier), _temperature(tier, temperature))


def get_second_opinion_model(
    settings: Settings, *, temperature: float | None = 0.0
) -> BaseChatModel:
    return build(settings, choose_second_opinion(settings), temperature)


def build(settings: Settings, choice: ModelChoice, temperature: float | None) -> BaseChatModel:
    kwargs: dict[str, Any] = {
        "timeout": settings.ai_timeout_seconds,
        "max_retries": settings.ai_max_retries,
    }
    if choice.api_key:
        kwargs["api_key"] = choice.api_key
    if choice.base_url:
        kwargs["base_url"] = choice.base_url
    if choice.api_version:
        kwargs["api_version"] = choice.api_version
    if temperature is not None:
        kwargs["temperature"] = temperature
    try:
        model: BaseChatModel = init_chat_model(
            model=choice.model, model_provider=choice.provider, **kwargs
        )
    except ImportError as exc:
        package = PROVIDER_PACKAGES.get(
            choice.provider, f"the LangChain package for {choice.provider}"
        )
        raise AINotConfigured(
            f"AI provider {choice.provider!r} needs {package}: add it to the `providers` extra "
            "in backend/pyproject.toml and run `pip install -e \".[providers]\"`"
        ) from exc
    return model


def _temperature(tier: Tier, override: float | None) -> float | None:
    return override if override is not None else DEFAULT_TEMPERATURE[tier]


def _require(choice: ModelChoice, model_var: str, provider_var: str, key_var: str) -> None:
    missing = []
    if not choice.provider:
        missing.append(provider_var)
    elif choice.provider not in PROVIDER_PACKAGES:
        raise AINotConfigured(
            f"{provider_var}={choice.provider!r} isn't supported; use one of "
            + ", ".join(sorted(PROVIDER_PACKAGES))
        )
    if not choice.model:
        missing.append(model_var)
    if not choice.api_key and choice.provider not in KEYLESS_PROVIDERS:
        missing.append(key_var)
    if missing:
        raise AINotConfigured(f"AI is not configured: set {', '.join(missing)} in backend/.env")
