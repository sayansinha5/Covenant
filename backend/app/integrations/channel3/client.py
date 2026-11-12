"""Channel3 product search. The API key stays on the server."""

from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.channel3.products import map_product, search_mode

logger = get_logger("covenant.channel3")


class CatalogError(Exception):
    def __init__(
        self, detail: str, *, status: int = 502, code: str = "CATALOG_UNAVAILABLE"
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.code = code


async def search_catalog(settings: Settings, query: str, *, org_id: str) -> list[dict[str, Any]]:
    key = settings.channel3_api_key.get_secret_value()
    if not key:
        raise CatalogError(
            "Add CHANNEL3_API_KEY to search the live product catalog.",
            status=503,
            code="CATALOG_NOT_CONFIGURED",
        )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0)) as http:
            response = await http.post(
                f"{settings.channel3_base_url.rstrip('/')}/v1/search",
                headers={
                    "x-api-key": key,
                    "x-user-id": org_id,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={"query": query, "limit": 8, "config": {"mode": search_mode(query)}},
            )
    except httpx.HTTPError as exc:
        logger.warning("channel3_unreachable", error_type=type(exc).__name__)
        raise CatalogError("Channel3 is not reachable right now.") from exc
    if response.status_code == 401:
        raise CatalogError(
            "Channel3 refused the API key. Check CHANNEL3_API_KEY.",
            status=503,
            code="CATALOG_NOT_CONFIGURED",
        )
    if response.status_code == 402:
        raise CatalogError("Channel3 credits are used up.", status=503, code="CATALOG_EXHAUSTED")
    if response.status_code >= 400:
        logger.warning("channel3_rejected", status_code=response.status_code)
        raise CatalogError("Channel3 could not search that query.")
    payload = response.json()
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list):
        raise CatalogError("Channel3 returned an unexpected response.")
    mapped = [item for item in (map_product(product) for product in products) if item is not None]
    return mapped
