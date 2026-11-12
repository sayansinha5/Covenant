"""Read-only Astropods account view: blueprints, deployments, and usage meters."""

from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger("covenant.astropods")


class AstropodsError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class AstropodsClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.astropods_base_url.rstrip("/")
        self.account = quote(settings.astropods_account.strip(), safe="")
        self.account_name = settings.astropods_account.strip()
        self.token = settings.astropods_api_token.get_secret_value()

    async def blueprints(self) -> list[dict[str, Any]]:
        payload = await self._get(f"/agents/{self.account}", {"limit": "50"})
        return [_blueprint(item) for item in _list(payload, "agents")]

    async def deployments(self) -> list[dict[str, Any]]:
        payload = await self._get(f"/accounts/{self.account}/deployments", {"limit": "50"})
        return [_deployment(item) for item in _list(payload, "deployments")]

    async def meters(self) -> list[dict[str, Any]]:
        payload = await self._get(f"/accounts/{self.account}/usage")
        raw = payload.get("meters") if isinstance(payload.get("meters"), dict) else {}
        meters: list[dict[str, Any]] = []
        for name, meter in raw.items():
            if not isinstance(meter, dict):
                continue
            usage = meter.get("usage")
            quota = meter.get("quota")
            meters.append(
                {
                    "name": str(name),
                    "usage": float(usage) if isinstance(usage, int | float) else 0.0,
                    "quota": float(quota) if isinstance(quota, int | float) else None,
                }
            )
        meters.sort(key=lambda item: item["usage"], reverse=True)
        return meters[:8]

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as http:
                response = await http.get(
                    f"{self.base_url}{path}",
                    params=params,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            logger.warning("astropods_unreachable", error_type=type(exc).__name__)
            raise AstropodsError("Astropods is not reachable right now.") from exc
        if response.status_code in (401, 403):
            raise AstropodsError(
                "Astropods refused the token. Run ast login and paste a fresh access token "
                "into ASTROPODS_API_TOKEN."
            )
        if response.status_code == 404:
            raise AstropodsError(f"Astropods has no account named {self.account_name}.")
        if response.status_code >= 400:
            logger.warning("astropods_rejected", status_code=response.status_code)
            raise AstropodsError("Astropods is unavailable.")
        payload = response.json()
        if not isinstance(payload, dict):
            raise AstropodsError("Astropods returned an unexpected response.")
        return payload


def _list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = payload.get(key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _blueprint(raw: dict[str, Any]) -> dict[str, Any]:
    metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    return {
        "uid": str(raw.get("uid") or ""),
        "name": str(raw.get("name") or ""),
        "deploys": int(metrics.get("deploy_count") or 0),
        "messages": int(metrics.get("lifetime_messages") or 0),
    }


def _deployment(raw: dict[str, Any]) -> dict[str, Any]:
    url = None
    for item in raw.get("external_urls") or []:
        if not isinstance(item, dict) or not item.get("ready"):
            continue
        candidate = item.get("url")
        if isinstance(candidate, str) and candidate.startswith("https://"):
            url = candidate
            break
    return {
        "id": str(raw.get("id") or ""),
        "name": str(raw.get("name") or ""),
        "display_name": str(raw.get("display_name") or raw.get("name") or ""),
        "status": str(raw.get("status") or "unknown"),
        "environment": str(raw.get("environment_name") or ""),
        "updated_at": raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None,
        "requests_recent": _series(raw.get("request_series")),
        "tokens_recent": _series(raw.get("token_series")),
        "url": url,
    }


def _series(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    numbers = [int(item) for item in value if isinstance(item, int) and not isinstance(item, bool)]
    return numbers[-12:]
