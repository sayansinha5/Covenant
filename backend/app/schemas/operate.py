"""Search, the settlement calendar, the product catalog and the agent fleet."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import RequestModel, ResponseModel


class SearchHit(ResponseModel):
    id: str
    kind: Literal["contract", "worker"]
    title: str
    subtitle: str
    href: str
    state: str


class SearchOut(ResponseModel):
    engine: Literal["elasticsearch", "database"]
    query: str
    items: list[SearchHit]


class ScheduleEvent(ResponseModel):
    id: str
    resource_id: str
    name: str
    kind: str
    start: datetime
    end: datetime
    contract_id: str


class ScheduleResourceOut(ResponseModel):
    id: str
    name: str
    state: str
    worker_name: str


class ScheduleOut(ResponseModel):
    generated_at: datetime
    resources: list[ScheduleResourceOut]
    events: list[ScheduleEvent]


class CatalogQuery(RequestModel):
    query: str = Field(min_length=2, max_length=200)


class CatalogOffer(ResponseModel):
    domain: str
    url: str | None
    price: str | None
    currency: str
    availability: str
    commission_percent: str | None


class CatalogProduct(ResponseModel):
    id: str
    title: str
    description: str
    brand: str
    image_url: str | None
    price_from: str | None
    currency: str
    offers: list[CatalogOffer]


class CatalogOut(ResponseModel):
    query: str
    products: list[CatalogProduct]


class FleetMeter(ResponseModel):
    name: str
    usage: float
    quota: float | None


class FleetDeployment(ResponseModel):
    id: str
    name: str
    display_name: str
    status: str
    environment: str
    updated_at: str | None
    requests_recent: list[int]
    tokens_recent: list[int]
    url: str | None
    matched_worker_id: str | None = None
    matched_worker_name: str | None = None


class FleetBlueprint(ResponseModel):
    uid: str
    name: str
    deploys: int
    messages: int


class FleetWorker(ResponseModel):
    id: str
    name: str
    kind: str
    status: str
    fleet_status: Literal["running", "published", "absent"]
    deployment_id: str | None


class FleetOut(ResponseModel):
    configured: bool
    account: str | None
    detail: str | None
    meters: list[FleetMeter]
    deployments: list[FleetDeployment]
    blueprints: list[FleetBlueprint]
    workers: list[FleetWorker]
