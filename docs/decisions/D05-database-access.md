# D5 — SQLAlchemy 2 async with asyncmy, Alembic migrations

**Status:** accepted

**Decision.** SQLAlchemy 2.x async ORM with the `asyncmy` driver; schema changes only through
Alembic, run as a dedicated migrator user. The app user gets DML grants per table after every
migration, and `ledger_entries` only INSERT/SELECT.

**Fallback.** The `aiomysql` driver.
