import httpx
import pytest
import respx

from covenant_mcp.client import CovenantClient

BASE = "http://api.test/api/v1"


def _client() -> tuple[CovenantClient, httpx.Client]:
    http = httpx.Client(base_url=BASE, headers={"Authorization": "Bearer ck_test"})
    return CovenantClient(BASE, "ck_test", client=http), http


@respx.mock
def test_find_workers_sends_the_key_and_filters() -> None:
    route = respx.get(f"{BASE}/workers").mock(return_value=httpx.Response(200, json={"items": []}))
    client, http = _client()
    try:
        assert client.find_workers("translation", max_price="40.00") == {"items": []}
    finally:
        http.close()
    assert route.called
    assert route.calls.last.request.headers["Authorization"] == "Bearer ck_test"
    assert route.calls.last.request.url.params["category"] == "translation"


@respx.mock
def test_a_revoked_key_surfaces_the_api_message() -> None:
    respx.get(f"{BASE}/mandate").mock(
        return_value=httpx.Response(401, json={"detail": "This API key isn't valid."})
    )
    client, http = _client()
    try:
        with pytest.raises(RuntimeError, match="isn't valid"):
            client.get_mandate()
    finally:
        http.close()
