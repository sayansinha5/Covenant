import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.logging import get_logger
from app.core.redaction import redact
from app.integrations.paypal.audit import (
    NullRecorder,
    Operation,
    OperationRecord,
    OperationRecorder,
)
from app.integrations.paypal.config import PayPalConfig
from app.integrations.paypal.errors import PayPalApiError, PayPalNetworkError, PayPalNotConfigured

TOKEN_PATH = "/v1/oauth2/token"  # noqa: S105  (a URL path, not a secret)
TOKEN_REFRESH_MARGIN_SECONDS = 60

logger = get_logger("covenant.paypal")


@dataclass(frozen=True)
class PayPalResponse:
    status: int
    body: Any
    debug_id: str | None


class PayPalHttp:
    """Transport for PayPal REST: OAuth token cache (single-flight refresh), idempotency
    headers, error mapping and the audit trail. No retries except one on an expired token."""

    def __init__(
        self,
        config: PayPalConfig,
        *,
        http: httpx.AsyncClient | None = None,
        recorder: OperationRecorder | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._http = http or httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            follow_redirects=False,
        )
        self._recorder: OperationRecorder = recorder or NullRecorder()
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def config(self) -> PayPalConfig:
        return self._config

    async def aclose(self) -> None:
        await self._http.aclose()

    def _token_valid(self) -> bool:
        return self._token is not None and self._clock() < self._token_expires_at

    async def access_token(self) -> str:
        if not self._config.configured:
            raise PayPalNotConfigured
        if self._token_valid():
            assert self._token is not None  # noqa: S101
            return self._token
        async with self._token_lock:
            if self._token_valid():
                assert self._token is not None  # noqa: S101
                return self._token
            try:
                response = await self._http.post(
                    TOKEN_PATH,
                    data={"grant_type": "client_credentials"},
                    auth=(self._config.client_id, self._config.client_secret),
                    headers={"Accept": "application/json"},
                )
            except httpx.TransportError as exc:
                raise PayPalNetworkError(
                    f"PayPal token request failed: {exc!r}", outcome_unknown=False
                ) from exc
            body = _json_or_text(response)
            if response.status_code != 200:
                raise PayPalApiError.from_body(
                    response.status_code, body, response.headers.get("PayPal-Debug-Id")
                )
            self._token = str(body["access_token"])
            expires_in = float(body["expires_in"])
            self._token_expires_at = self._clock() + expires_in - TOKEN_REFRESH_MARGIN_SECONDS
            return self._token

    def _invalidate_token(self) -> None:
        self._token = None
        self._token_expires_at = 0.0

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        operation: Operation | None = None,
    ) -> PayPalResponse:
        """Send one call. Mutating calls must pass `operation`, which supplies the
        PayPal-Request-Id and is written to the audit trail whatever the outcome."""
        response: httpx.Response | None = None
        for attempt in (1, 2):
            headers = {
                "Authorization": f"Bearer {await self.access_token()}",
                "Accept": "application/json",
            }
            if operation is not None:
                headers["PayPal-Request-Id"] = operation.request_id
                headers["Prefer"] = "return=representation"
            try:
                response = await self._http.request(method, path, json=json, headers=headers)
            except httpx.TransportError as exc:
                # A connect failure never reached PayPal; anything later might have.
                unknown = not isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout)
                await self._record(operation, method, path, json, None, {"error": repr(exc)}, None)
                logger.warning(
                    "paypal_network_error", path=path, outcome_unknown=unknown, error=repr(exc)
                )
                raise PayPalNetworkError(
                    f"PayPal {method} {path} failed: {exc!r}", outcome_unknown=unknown
                ) from exc
            if response.status_code == 401 and attempt == 1:
                self._invalidate_token()
                continue
            break
        assert response is not None  # noqa: S101

        body = _json_or_text(response)
        debug_id = response.headers.get("PayPal-Debug-Id")
        await self._record(operation, method, path, json, response.status_code, body, debug_id)
        logger.info(
            "paypal_call",
            method=method,
            path=path,
            status=response.status_code,
            paypal_debug_id=debug_id,
            request_id=operation.request_id if operation else None,
        )
        if response.status_code >= 400:
            raise PayPalApiError.from_body(response.status_code, body, debug_id)
        return PayPalResponse(status=response.status_code, body=body, debug_id=debug_id)

    async def _record(
        self,
        operation: Operation | None,
        method: str,
        path: str,
        request_body: Any,
        status: int | None,
        response_body: Any,
        debug_id: str | None,
    ) -> None:
        if operation is None:
            return
        await self._recorder.record(
            OperationRecord(
                operation=operation,
                http_method=method,
                path=path,
                request_body=redact(request_body),
                response_status=status,
                response_body=redact(response_body),
                paypal_debug_id=debug_id,
            )
        )


def _json_or_text(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text[:2000]
