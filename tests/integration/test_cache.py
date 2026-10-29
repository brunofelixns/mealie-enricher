import shutil
import sqlite3
from contextlib import closing

from alembic.config import Config
from sqlalchemy import text

from alembic import command
from mealie_enricher.models import NutrientSet
from mealie_enricher.storage.cache import SqliteCache
from tests.parity.cases import FIXTURES


async def test_malformed_cached_json_is_a_miss_for_both_sources(cache):
    async with cache.engine.begin() as connection:
        for table in ("nutrient_cache", "llm_nutrient_cache"):
            await connection.execute(
                text(
                    f"INSERT INTO {table} (food_name,nutrients,updated_at) VALUES (:food,:raw,:now)"
                ),
                {"food": "broken", "raw": "{", "now": int(cache.clock_ms())},
            )
    assert await cache.get_nutrients("broken") is None
    assert await cache.get_llm_nutrients("broken") is None


async def test_cache_round_trip_normalization_expiry_and_reopen(tmp_path):
    now = [1700000000000]
    path = tmp_path / "cache.db"
    cache = await SqliteCache.open(str(path), 1000, clock_ms=lambda: now[0])
    await cache.set_nutrients(" Rice ", NutrientSet(kcalPer100g=100, fatPer100g=0))
    await cache.set_grams(" Cup ", " Rice ", 240)
    await cache.set_llm_nutrients(" Rice ", NutrientSet(kcalPer100g=90))
    assert (await cache.get_nutrients("rice")).fat_per100g == 0
    assert await cache.get_grams("cup", "rice") == 240
    assert (await cache.get_llm_nutrients("rice")).kcal_per100g == 90
    await cache.close()
    cache = await SqliteCache.open(str(path), 1000, clock_ms=lambda: now[0])
    assert (await cache.get_nutrients("rice")).kcal_per100g == 100
    now[0] += 1001
    assert await cache.get_nutrients("rice") is None
    assert await cache.get_grams("cup", "rice") is None
    await cache.close()


async def test_alembic_preserves_rows_in_database_exported_by_original(tmp_path):
    path = tmp_path / "legacy.db"
    shutil.copyfile(FIXTURES / "legacy-cache.db", path)
    with closing(sqlite3.connect(path)) as database:
        before = database.execute("SELECT * FROM nutrient_cache ORDER BY food_name").fetchall()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", "sqlite:///" + path.as_posix())
    command.upgrade(config, "head")
    with closing(sqlite3.connect(path)) as database:
        assert (
            database.execute("SELECT * FROM nutrient_cache ORDER BY food_name").fetchall() == before
        )
        assert database.execute("SELECT version_num FROM alembic_version").fetchone() == ("0001",)
    cache = await SqliteCache.open(str(path), 86400000, clock_ms=lambda: 1700000003500)
    assert (await cache.get_nutrients("rice")).kcal_per100g == 100
    await cache.close()
