import asyncio
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import ConfigurationError, Settings, load_settings
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import (
    MAX_JSON_BODY_BYTES,
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
)
from app.core.rate_limit import RateLimiter
from app.core.security import TokenIssuer
from app.db.engine import Database, DatabaseUnavailable
from app.integrations.paypal import PayPalClient, PayPalConfig
from app.runner import build_runner
from app.services.paypal_audit import SqlOperationRecorder

logger = get_logger("covenant.app")


def _build_lifespan(
    settings: Settings, database: Database, paypal: PayPalClient
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            await database.ping()
        except DatabaseUnavailable as exc:
            logger.error(
                "startup_failed",
                reason=str(exc),
                hint="Check DB_HOST, DB_USER and DB_PASSWORD in .env and backend/.env, "
                "and that MySQL is running.",
            )
            raise
        logger.info("startup_complete", database=database.describe())
        stop = asyncio.Event()
        embedded = (
            asyncio.create_task(build_runner(settings, database, paypal).run_forever(stop))
            if settings.runner_embedded
            else None
        )
        yield
        if embedded is not None:
            stop.set()
            await embedded
        await paypal.aclose()
        await database.dispose()

    return lifespan


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    paypal: PayPalClient | None = None,
) -> FastAPI:
    if settings is None:
        try:
            settings = load_settings()
        except ConfigurationError as exc:
            print(f"Covenant API cannot start.\n{exc}", file=sys.stderr)  # noqa: T201
            raise SystemExit(1) from None

    setup_logging(settings.log_level, json_output=settings.app_env != "development")
    database = database or Database.from_settings(settings)
    paypal = paypal or PayPalClient(
        PayPalConfig.from_settings(settings), recorder=SqlOperationRecorder(database)
    )
    is_dev = settings.app_env == "development"

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=_build_lifespan(settings, database, paypal),
        docs_url="/docs" if is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if is_dev else None,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.paypal = paypal
    app.state.rate_limiter = RateLimiter()
    app.state.token_issuer = TokenIssuer(
        secret=settings.jwt_secret.get_secret_value(),
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl=timedelta(minutes=settings.access_token_ttl_minutes),
    )

    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Request-ID",
            "X-Requested-With",
        ],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_JSON_BODY_BYTES)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_router)
    return app
