"""A small Elasticsearch client. httpx, so the backend image stays free of the official SDK."""

import json
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.elastic.query import elasticsearch_endpoint, search_request

INDEX = "covenant-work"
logger = get_logger("covenant.elastic")

_MAPPING: dict[str, Any] = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "kind": {"type": "keyword"},
            "title": {"type": "text"},
            "subtitle": {"type": "text"},
            "body": {"type": "text"},
            "href": {"type": "keyword", "index": False},
            "state": {"type": "keyword"},
            "ref_id": {"type": "keyword", "index": False},
        }
    },
}


class ElasticError(Exception):
    """The cluster could not answer. Search falls back to the database."""


class ElasticClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = elasticsearch_endpoint(
            settings.elasticsearch_url, settings.elastic_cloud_id
        )
        self.api_key = settings.elastic_api_key.get_secret_value()

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(0.8)) as http:
                response = await http.get(f"{self.base_url}/", headers=self._headers())
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def search_documents(
        self, documents: list[dict[str, Any]], query: str
    ) -> list[dict[str, Any]]:
        if not documents:
            return []
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as http:
            await self._ensure_index(http)
            await self._bulk(http, documents)
            return await self._search(http, documents, query)

    async def _ensure_index(self, http: httpx.AsyncClient) -> None:
        response = await self._send(http, "PUT", f"/{INDEX}", json_body=_MAPPING)
        if response.status_code in (200, 201):
            return
        if response.status_code == 400 and "resource_already_exists_exception" in response.text:
            return
        raise ElasticError("index")

    async def _bulk(self, http: httpx.AsyncClient, documents: list[dict[str, Any]]) -> None:
        lines: list[str] = []
        for document in documents:
            lines.append(json.dumps({"index": {"_index": INDEX, "_id": document["doc_id"]}}))
            source = {key: value for key, value in document.items() if key != "doc_id"}
            lines.append(json.dumps(source))
        body = ("\n".join(lines) + "\n").encode()
        response = await self._send(
            http,
            "POST",
            f"/{INDEX}/_bulk?refresh=wait_for",
            content=body,
            content_type="application/x-ndjson",
        )
        if response.status_code >= 300:
            raise ElasticError("bulk")
        payload = response.json()
        if isinstance(payload, dict) and payload.get("errors"):
            raise ElasticError("bulk")

    async def _search(
        self, http: httpx.AsyncClient, documents: list[dict[str, Any]], query: str
    ) -> list[dict[str, Any]]:
        response = await self._send(
            http,
            "POST",
            f"/{INDEX}/_search",
            json_body=search_request(query, [document["doc_id"] for document in documents]),
        )
        if response.status_code >= 300:
            raise ElasticError("search")
        payload = response.json()
        hits = payload.get("hits", {}).get("hits", []) if isinstance(payload, dict) else []
        found: list[dict[str, Any]] = []
        for hit in hits:
            source = hit.get("_source") if isinstance(hit, dict) else None
            if isinstance(source, dict) and source.get("ref_id"):
                found.append(
                    {
                        "id": source["ref_id"],
                        "kind": source.get("kind") or "",
                        "title": source.get("title") or "",
                        "subtitle": source.get("subtitle") or "",
                        "href": source.get("href") or "",
                        "state": source.get("state") or "",
                    }
                )
        return found

    async def _send(
        self,
        http: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> httpx.Response:
        try:
            return await http.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(
                    content_type or ("application/json" if json_body is not None else None)
                ),
                json=dict(json_body) if json_body is not None else None,
                content=content,
            )
        except httpx.HTTPError as exc:
            logger.warning("elastic_request_failed", error_type=type(exc).__name__)
            raise ElasticError("network") from exc
