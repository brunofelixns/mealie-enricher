"""The same persistence contract against SQLite and isolated PostgreSQL schemas."""

import os
import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from mealie_enricher.app import create_app
from mealie_enricher.config import load_settings
from mealie_enricher.models import NutrientSet
from mealie_enricher.storage.cache import SqliteCache


@pytest.fixture(params=["sqlite", "postgresql"])
async def database_url(request, tmp_path):
    if request.param == "sqlite":
        yield URL.create(
            "sqlite+aiosqlite", database=str(tmp_path / "runtime.db")
        ).render_as_string()
        return
    configured = os.getenv("TEST_POSTGRES_URL")
    if not configured:
        pytest.skip("Set TEST_POSTGRES_URL to exercise a real PostgreSQL server")
    url = make_url(configured).set(drivername="postgresql+psycopg")
    schema = "enricher_test_" + uuid.uuid4().hex
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        yield url.update_query_dict({"options": "-csearch_path=" + schema}).render_as_string(
            hide_password=False
        )
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await engine.dispose()


async def test_database_cache_upserts_expiry_and_reopen(database_url, tmp_path):
    now = [1700000000000]
    path = str(tmp_path / "unused.db")
    cache = await SqliteCache.open(path, 1000, database_url=database_url, clock_ms=lambda: now[0])
    try:
        await cache.set_nutrients(" Rice ", NutrientSet(kcal_per100g=100))
        await cache.set_nutrients("rice", NutrientSet(kcal_per100g=120, fat_per100g=0))
        await cache.set_grams("Cup", "Rice", 240)
        await cache.set_grams("Cup", "Rice", 250)
        await cache.set_llm_nutrients("rice", NutrientSet(kcal_per100g=110))
    finally:
        await cache.close()
    cache = await SqliteCache.open(path, 1000, database_url=database_url, clock_ms=lambda: now[0])
    try:
        assert (await cache.get_nutrients("rice")).kcal_per100g == 120
        assert (await cache.get_nutrients("rice")).fat_per100g == 0
        assert await cache.get_grams("cup", "rice") == 250
        assert (await cache.get_llm_nutrients("rice")).kcal_per100g == 110
        now[0] += 1001
        assert await cache.get_nutrients("rice") is None
        assert await cache.get_grams("cup", "rice") is None
    finally:
        await cache.close()


def settings_for(database_url, tmp_path, **extra):
    return load_settings(
        {
            "MEALIE_API_TOKEN": "synthetic",
            "DATABASE_URL": database_url,
            "CACHE_DB_PATH": str(tmp_path / "unused.db"),
            **extra,
        }
    )


async def history_response(app, query=""):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app.test"
    ) as client:
        return await client.get("/estimator/history.json" + query)


async def test_history_survives_restart_and_more_than_one_day(database_url, tmp_path):
    now = [1700000000000]
    settings = settings_for(database_url, tmp_path)
    app = create_app(settings, clock_ms=lambda: now[0])
    async with app.router.lifespan_context(app):
        handle = app.state.history.record_start("estimate", "rice")
        handle.set_recipe("Arroz", "household")
        now[0] += 50
        handle.complete("processed", ["Saved nutrition"])
        original = (await history_response(app)).json()
    now[0] += 86400001
    app = create_app(settings, clock_ms=lambda: now[0])
    async with app.router.lifespan_context(app):
        assert (await history_response(app)).json() == original
        assert original[0]["recipeName"] == "Arroz"
        assert original[0]["durationMs"] == 50


async def test_pagination_preserves_older_and_evicted_running_executions(database_url, tmp_path):
    now = [1700000000000]
    app = create_app(
        settings_for(database_url, tmp_path, HISTORY_MAX_ENTRIES="2"), clock_ms=lambda: now[0]
    )
    async with app.router.lifespan_context(app):
        first = app.state.history.record_start("webhook", "first")
        for slug in ("second", "third"):
            now[0] += 1
            app.state.history.record_start("estimate", slug).complete("skipped", [])
        first.complete("processed", ["Completed after page eviction"])
        assert len((await history_response(app)).json()) == 2
        older = (await history_response(app, "?limit=2&offset=2")).json()
        assert len(older) == 1
        assert older[0]["slug"] == "first"
        assert older[0]["status"] == "processed"
        assert (await history_response(app, f"?since={now[0]}")).json() == []
        for query in ("?limit=0", "?limit=1001", "?offset=-1", "?limit=nope"):
            assert (await history_response(app, query)).status_code == 400


async def test_restart_marks_unfinished_execution_as_interrupted(database_url, tmp_path):
    settings = settings_for(database_url, tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.history.record_start("backfill", "interrupted")
        assert (await history_response(app)).json()[0]["status"] == "running"
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        record = (await history_response(app)).json()[0]
        assert record["status"] == "error"
        assert "interrupt" in record["error"].lower()
        assert record["finishedAt"] is not None


async def test_retention_removes_finished_history_but_keeps_active_work(database_url, tmp_path):
    now = [1700000000000]
    app = create_app(
        settings_for(database_url, tmp_path, HISTORY_RETENTION_DAYS="1"), clock_ms=lambda: now[0]
    )
    async with app.router.lifespan_context(app):
        app.state.history.record_start("estimate", "old").complete("processed", [])
        app.state.history.record_start("webhook", "running")
        assert len((await history_response(app)).json()) == 2
        now[0] += 86400001
        records = (await history_response(app)).json()
        assert [record["slug"] for record in records] == ["running"]


async def test_processing_persists_without_a_history_reader(database_url, tmp_path):
    settings = settings_for(database_url, tmp_path, ESTIMATE_STRATEGY="tagged")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"slug": "filtered", "tags": []})
        )
    ) as http:
        app = create_app(settings, http=http)
        async with app.router.lifespan_context(app):
            await app.state.processing.process_estimate("filtered")
        app = create_app(settings, http=http)
        async with app.router.lifespan_context(app):
            records = (await history_response(app)).json()
            assert records[0]["status"] == "filtered"


async def test_database_failure_on_shutdown_still_closes_owned_http(database_url, tmp_path):
    app = create_app(settings_for(database_url, tmp_path))
    with pytest.raises(SQLAlchemyError):
        async with app.router.lifespan_context(app):
            owned_http = app.state.http
            app.state.history.record_start("estimate", "pending")
            async with app.state.cache.engine.begin() as connection:
                await connection.execute(text("DROP TABLE execution_history"))
    assert owned_http.is_closed


async def test_since_poll_includes_completions_beyond_the_initial_page(database_url, tmp_path):
    now = [1700000000000]
    app = create_app(
        settings_for(database_url, tmp_path, HISTORY_MAX_ENTRIES="2"), clock_ms=lambda: now[0]
    )
    async with app.router.lifespan_context(app):
        first = app.state.history.record_start("estimate", "long-running")
        previous_watermark = (await history_response(app)).json()[0]["updatedAt"]
        now[0] += 1
        first.complete("processed", [])
        for slug in ("newer-one", "newer-two"):
            now[0] += 1
            app.state.history.record_start("estimate", slug).complete("processed", [])
        deltas = (await history_response(app, f"?since={previous_watermark}")).json()
        assert {record["slug"] for record in deltas} == {"long-running", "newer-one", "newer-two"}
        assert all(record["status"] == "processed" for record in deltas)
