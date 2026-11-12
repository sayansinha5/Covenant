import base64
from datetime import UTC, datetime, timedelta

import pytest
import respx
from pydantic import ValidationError

from app.domain.schedule import ScheduleContract, build_schedule
from app.integrations.astropods.client import AstropodsClient, AstropodsError
from app.integrations.astropods.match import names_match
from app.integrations.channel3.client import CatalogError, search_catalog
from app.integrations.channel3.products import map_product, search_mode
from app.integrations.elastic.query import (
    elasticsearch_endpoint,
    filter_documents,
    search_request,
)
from tests.conftest import make_settings

CREATED = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
PRODUCT = {
    "id": "sku-1",
    "title": "Kantha stole",
    "description": "Hand stitched silk.",
    "brands": [{"name": "Kantha & Co"}],
    "images": [{"url": "https://cdn.example/stole.jpg"}],
    "offers": [
        {
            "domain": "shop.example",
            "url": "https://shop.example/stole",
            "price": {"price": 48, "currency": "USD"},
            "availability": "in_stock",
            "max_commission_rate": 0.05,
        },
        {
            "domain": "other.example",
            "url": "javascript:alert(1)",
            "price": {"price": 52.5, "currency": "USD"},
            "availability": "in_stock",
            "max_commission_rate": 0,
        },
    ],
}


def test_cloud_id_becomes_an_https_host() -> None:
    encoded = base64.b64encode(b"example.com$es-host$kibana-host").decode()
    assert elasticsearch_endpoint("", f"covenant:{encoded}") == "https://es-host.example.com"
    assert elasticsearch_endpoint("http://elasticsearch:9200", "") == "http://elasticsearch:9200"


def test_a_broken_cloud_id_is_refused_at_startup() -> None:
    with pytest.raises(ValidationError, match="ELASTIC_CLOUD_ID"):
        make_settings(elastic_cloud_id="covenant:not-base64")


def test_search_request_requires_every_word_inside_the_loaded_ids() -> None:
    body = search_request("german listings", ["contract:1"])
    assert body["query"]["bool"]["must"]["multi_match"]["operator"] == "and"
    assert body["query"]["bool"]["filter"]["ids"]["values"] == ["contract:1"]


def test_database_search_keeps_documents_that_contain_every_word() -> None:
    documents = [
        _doc("1", "C-9 German listings", "Lipi", "translate the stole listings"),
        _doc("2", "C-8 Portrait", "Arjun", "a poster of a loom"),
    ]
    found = filter_documents(documents, "German stole")
    assert [item["id"] for item in found] == ["1"]


def test_a_sentence_uses_the_agentic_catalog_search() -> None:
    assert search_mode("silk stole") == "default"
    assert search_mode("silk kantha stole under eighty dollars for a listing") == "agentic"


def test_product_mapping_drops_unsafe_links_and_keeps_the_cheapest_price() -> None:
    product = map_product(PRODUCT)
    assert product is not None
    assert product["brand"] == "Kantha & Co"
    assert product["price_from"] == "48.00"
    assert product["offers"][0]["commission_percent"] == "5"
    assert product["offers"][1]["url"] is None
    assert map_product({"id": "x"}) is None


def test_worker_names_match_a_deployment_suffix_but_not_a_short_token() -> None:
    assert names_match("Lipi", "lipi-translator")
    assert not names_match("AI", "covenant-lipi")
    assert not names_match("Tally", "QuickWordz")


def test_schedule_draws_the_hold_the_deadline_and_an_early_authorization() -> None:
    resources, windows = build_schedule(
        [
            ScheduleContract(
                contract_id="c1",
                number="C-1001",
                title="Translate the stole listings",
                state="in_progress",
                worker_name="Lipi",
                created_at=CREATED,
                accept_by_at=CREATED + timedelta(minutes=30),
                deadline_at=CREATED + timedelta(hours=6),
                appeal_window_ends_at=None,
                honor_period_ends_at=CREATED + timedelta(days=3),
                auth_expires_at=CREATED + timedelta(days=1),
            )
        ],
        appeal_window=timedelta(minutes=60),
    )
    assert resources[0].name.startswith("C-1001 · Lipi")
    kinds = {window.kind: window for window in windows}
    assert set(kinds) == {"accept", "delivery", "honor", "reauthorize"}
    assert kinds["delivery"].end == CREATED + timedelta(hours=6)
    assert kinds["reauthorize"].end == CREATED + timedelta(days=1)
    assert kinds["honor"].start == CREATED


def test_an_authorization_that_ends_with_the_hold_is_not_drawn_twice() -> None:
    _, windows = build_schedule(
        [
            ScheduleContract(
                contract_id="c1",
                number="C-1001",
                title="Listings",
                state="funded",
                worker_name="Lipi",
                created_at=CREATED,
                accept_by_at=None,
                deadline_at=None,
                appeal_window_ends_at=CREATED + timedelta(hours=2),
                honor_period_ends_at=CREATED + timedelta(days=3),
                auth_expires_at=CREATED + timedelta(days=3),
            )
        ],
        appeal_window=timedelta(minutes=60),
    )
    kinds = {window.kind for window in windows}
    assert kinds == {"appeal", "honor"}
    appeal = next(window for window in windows if window.kind == "appeal")
    assert appeal.start == CREATED + timedelta(hours=1)


@respx.mock
async def test_catalog_search_sends_the_key_and_maps_the_product() -> None:
    route = respx.post("https://api.trychannel3.com/v1/search").respond(
        json={"products": [PRODUCT]}
    )
    products = await search_catalog(
        make_settings(channel3_api_key="channel3-test"), "silk stole", org_id="org-1"
    )
    assert products[0]["title"] == "Kantha stole"
    assert route.calls[0].request.headers["x-api-key"] == "channel3-test"
    assert route.calls[0].request.headers["x-user-id"] == "org-1"


@respx.mock
async def test_catalog_search_reports_a_refused_key() -> None:
    respx.post("https://api.trychannel3.com/v1/search").respond(status_code=401)
    with pytest.raises(CatalogError, match="CHANNEL3_API_KEY") as caught:
        await search_catalog(make_settings(channel3_api_key="bad"), "silk stole", org_id="org-1")
    assert caught.value.status == 503


@respx.mock
async def test_fleet_client_reads_deployments_and_usage() -> None:
    respx.get("https://astropods.com/api/v1/accounts/covenant/deployments").respond(
        json={
            "deployments": [
                {
                    "id": "dep-1",
                    "name": "lipi",
                    "display_name": "Lipi",
                    "status": "running",
                    "environment_name": "main",
                    "request_series": [1, 4, 2],
                    "token_series": [10],
                    "external_urls": [
                        {"ready": True, "url": "https://lipi.example"},
                        {"ready": True, "url": "http://insecure.example"},
                    ],
                }
            ]
        }
    )
    respx.get("https://astropods.com/api/v1/accounts/covenant/usage").respond(
        json={"meters": {"tokens": {"usage": 12, "quota": 100}, "ignored": "no"}}
    )
    client = AstropodsClient(
        make_settings(astropods_api_token="astropods-test", astropods_account="covenant")
    )
    deployments = await client.deployments()
    meters = await client.meters()
    assert deployments[0]["url"] == "https://lipi.example"
    assert deployments[0]["requests_recent"] == [1, 4, 2]
    assert meters[0] == {"name": "tokens", "usage": 12.0, "quota": 100.0}


@respx.mock
async def test_fleet_client_explains_a_refused_token() -> None:
    respx.get("https://astropods.com/api/v1/agents/covenant").respond(status_code=401)
    client = AstropodsClient(
        make_settings(astropods_api_token="stale", astropods_account="covenant")
    )
    with pytest.raises(AstropodsError, match="ast login"):
        await client.blueprints()


def _doc(ref_id: str, title: str, subtitle: str, body: str) -> dict[str, str]:
    return {
        "doc_id": f"contract:{ref_id}",
        "ref_id": ref_id,
        "kind": "contract",
        "title": title,
        "subtitle": subtitle,
        "body": body,
        "href": f"/contracts/{ref_id}",
        "state": "in_progress",
    }
