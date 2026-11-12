"""HTTP calls the MCP tools make. The API key is a bearer token."""

from typing import Any

import httpx


class CovenantClient:
    def __init__(self, base_url: str, api_key: str, *, client: httpx.Client | None = None) -> None:
        self._owns = client is None
        self.http = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )

    def close(self) -> None:
        if self._owns:
            self.http.close()

    def find_workers(
        self, category: str, *, max_price: str | None = None, min_reputation: int | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"category": category}
        if max_price:
            params["max_price"] = max_price
        if min_reputation is not None:
            params["min_reputation"] = min_reputation
        return self._json("GET", "/workers", params=params)

    def propose_contract(
        self, worker_id: str, request_text: str, budget: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"worker_id": worker_id, "request_text": request_text}
        if budget:
            body["budget"] = budget
        return self._json("POST", "/contracts", json=body)

    def get_contract(self, contract_id: str) -> dict[str, Any]:
        return self._json("GET", f"/contracts/{contract_id}")

    def fund_contract(self, contract_id: str) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/contracts/{contract_id}/agree",
            headers={"Idempotency-Key": f"mcp-{contract_id}"},
        )

    def cancel_contract(self, contract_id: str) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/contracts/{contract_id}/cancel",
            headers={"Idempotency-Key": f"mcp-cancel-{contract_id}"},
        )

    def get_mandate(self) -> dict[str, Any]:
        return self._json("GET", "/mandate")

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.http.request(method, path, **kwargs)
        if response.status_code >= 400:
            detail = ""
            try:
                detail = str(response.json().get("detail") or response.text)
            except ValueError:
                detail = response.text
            raise RuntimeError(detail[:400] or f"HTTP {response.status_code}")
        body: dict[str, Any] = response.json()
        return body
