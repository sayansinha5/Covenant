from datetime import UTC, datetime

from sqlalchemy import CHAR, MetaData, Numeric
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

UtcDateTime = DATETIME(fsp=6)
Money = Numeric(12, 2, asdecimal=True)


def utcnow() -> datetime:
    """Naive UTC with microseconds, matching DATETIME(6) columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UuidPrimaryKey:
    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid7)
