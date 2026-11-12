from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.deps import get_app_settings, get_database
from app.core.config import Settings
from app.db.engine import Database, DatabaseUnavailable
from app.integrations.elastic.client import ElasticClient

router = APIRouter(tags=["health"])


class HealthComponents(BaseModel):
    database: Literal["ok", "error"]
    paypal: Literal["configured", "not_configured"]
    ai: Literal["configured", "not_configured"]
    langsmith: Literal["on", "off"]
    channel3: Literal["configured", "not_configured"]
    astropods: Literal["configured", "not_configured"]
    elastic: Literal["ok", "unreachable", "not_configured"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    environment: str
    paypal_env: str
    components: HealthComponents


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Settings = Depends(get_app_settings),
    database: Database = Depends(get_database),
) -> JSONResponse:
    try:
        await database.ping()
        db_status: Literal["ok", "error"] = "ok"
    except DatabaseUnavailable:
        db_status = "error"

    body = HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        environment=settings.app_env,
        paypal_env=settings.paypal_env,
        components=HealthComponents(
            database=db_status,
            paypal="configured" if settings.paypal_configured else "not_configured",
            ai="configured" if settings.ai_configured else "not_configured",
            langsmith="on" if settings.langsmith_enabled else "off",
            channel3="configured" if settings.channel3_configured else "not_configured",
            astropods="configured" if settings.astropods_configured else "not_configured",
            elastic=await _elastic_status(settings),
        ),
    )
    return JSONResponse(body.model_dump(), status_code=200 if db_status == "ok" else 503)


async def _elastic_status(settings: Settings) -> Literal["ok", "unreachable", "not_configured"]:
    if not settings.elastic_configured:
        return "not_configured"
    if await ElasticClient(settings).ping():
        return "ok"
    return "unreachable"
