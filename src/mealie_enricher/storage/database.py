"""Shared database URL, migrations and conflict updates for runtime storage."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import Connection, Table
from sqlalchemy.dialects.postgresql import Insert as PostgresInsert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import Insert as SqliteInsert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import command


def connection_url(configured: str, sqlite_path: str) -> URL:
    url = (
        make_url(configured) if configured else URL.create("sqlite+aiosqlite", database=sqlite_path)
    )
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg"}:
        return url.set(drivername="postgresql+psycopg")
    if url.drivername in {"sqlite", "sqlite+aiosqlite"}:
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        return url.set(drivername="sqlite+aiosqlite")
    raise ValueError("DATABASE_URL must use PostgreSQL (psycopg) or SQLite")


def create_database_engine(configured: str, sqlite_path: str) -> AsyncEngine:
    url = connection_url(configured, sqlite_path)
    return create_async_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        **(
            {"connect_args": {"connect_timeout": 10}}
            if url.get_backend_name() == "postgresql"
            else {}
        ),
    )


async def migrate_database(engine: AsyncEngine) -> None:
    def upgrade(connection: Connection) -> None:
        location = Path(__file__).resolve().parents[3] / "alembic.ini"
        if not location.exists():
            location = Path.cwd() / "alembic.ini"
        config = Config(str(location))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    async with engine.begin() as connection:
        await connection.run_sync(upgrade)


def conflict_insert(engine: AsyncEngine, table: Table) -> PostgresInsert | SqliteInsert:
    return postgres_insert(table) if engine.dialect.name == "postgresql" else sqlite_insert(table)
