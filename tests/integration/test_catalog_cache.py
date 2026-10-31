from sqlalchemy import text

from mealie_enricher.catalog.models import CatalogFood, CatalogResolution
from mealie_enricher.models import NutrientSet
from mealie_enricher.storage.cache import SqliteCache


async def test_catalog_resolution_cache_persists_expires_and_preserves_unknowns(tmp_path):
    now = [1000]
    path = str(tmp_path / "cache.db")
    cache = await SqliteCache.open(path, 100, clock_ms=lambda: now[0])
    resolution = CatalogResolution(
        status="matched",
        food=CatalogFood(
            id="bedca:1",
            source="bedca",
            source_id="1",
            name="Arroz crudo",
            nutrients=NutrientSet(kcal_per100g=350),
            state="raw",
        ),
    )
    await cache.set_catalog_resolution("context:v1", resolution)
    assert await cache.get_catalog_resolution("context:v2") is None
    await cache.close()
    cache = await SqliteCache.open(path, 100, clock_ms=lambda: now[0])
    found = await cache.get_catalog_resolution("context:v1")
    assert found.food.nutrients.protein_per100g is None
    now[0] = 1101
    assert await cache.get_catalog_resolution("context:v1") is None
    await cache.close()


async def test_corrupt_catalog_cache_is_a_miss(cache):
    async with cache.engine.begin() as conn:
        for key, raw in (("bad-json", "{"), ("bad-shape", '{"status":"matched"}')):
            await conn.execute(
                text("INSERT INTO catalog_resolution_cache VALUES (:key, :value, :now)"),
                {"key": key, "value": raw, "now": cache.clock_ms()},
            )
    assert await cache.get_catalog_resolution("bad-json") is None
    assert await cache.get_catalog_resolution("bad-shape") is None
