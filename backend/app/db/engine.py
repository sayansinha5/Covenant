from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

DRIVER = "mysql+asyncmy"


class DatabaseUnavailable(RuntimeError):
    pass


def database_url(settings: Settings, *, migrator: bool = False, test: bool = False) -> URL:
    user = settings.db_migrator_user if migrator else settings.db_user
    password = settings.db_migrator_password if migrator else settings.db_password
    return URL.create(
        DRIVER,
        username=user,
        password=password.get_secret_value(),
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_test_name if test else settings.db_name,
        query={"charset": "utf8mb4"},
    )


class Database:
    """Owns the async engine and session factory for one process (api, runner or a script)."""

    def __init__(self, url: URL, *, pool_size: int = 10) -> None:
        self.url = url
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=pool_size,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @classmethod
    def from_settings(cls, settings: Settings, *, test: bool = False) -> "Database":
        return cls(database_url(settings, test=test), pool_size=settings.db_pool_size)

    def describe(self) -> str:
        return f"{self.url.username}@{self.url.host}:{self.url.port}/{self.url.database}"

    async def ping(self) -> None:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:
            raise DatabaseUnavailable(f"Cannot reach MySQL as {self.describe()}: {exc}") from exc

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
