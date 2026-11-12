"""One OpenAI-compatible chat call. Demo workers only need a completion, not a framework."""

import json

import httpx

from common.settings import Settings

BASES = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://127.0.0.1:11434/v1",
}
KEYLESS = frozenset({"ollama"})


class LLMError(RuntimeError):
    pass


async def complete(settings: Settings, system: str, user: str) -> str:
    provider = settings.ai_provider
    base = settings.ai_base_url.rstrip("/") or BASES.get(provider, "")
    if not base:
        raise LLMError(
            f"AI_PROVIDER={provider!r} isn't an OpenAI-compatible provider. "
            "Use openai, groq or ollama, or set AI_BASE_URL."
        )
    model = settings.ai_fast or settings.ai_model
    key = settings.ai_api_key.get_secret_value()
    if not model or (not key and provider not in KEYLESS):
        raise LLMError("Set AI_MODEL and AI_API_KEY (ollama needs no key).")
    try:
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as http:
            response = await http.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key or 'ollama'}"},
                json={
                    "model": model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
    except httpx.HTTPError as exc:
        raise LLMError(f"The model request failed: {exc}") from exc
    if response.status_code != 200:
        raise LLMError(f"The model answered HTTP {response.status_code}.")
    content = response.json()["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise LLMError("The model returned an empty answer.")
    return content


def parse_json(text: str) -> object:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError("The model didn't return JSON.") from exc
