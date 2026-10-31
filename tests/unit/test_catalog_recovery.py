from unittest.mock import AsyncMock

from mealie_enricher.catalog.models import CatalogFood, CatalogQuery
from mealie_enricher.catalog.resolver import CatalogResolver
from mealie_enricher.models import NutrientSet


async def test_decisions_failure_can_recover_without_waiting_for_cache_expiry():
    foods = [
        CatalogFood(
            id="raw",
            source="test",
            source_id="1",
            name="Arroz crudo",
            state="raw",
            nutrients=NutrientSet(kcal_per100g=350),
        ),
        CatalogFood(
            id="cooked",
            source="test",
            source_id="2",
            name="Arroz cocido",
            state="cooked",
            nutrients=NutrientSet(kcal_per100g=130),
        ),
    ]

    class Reader:
        fingerprint = "test-v1"

        def search(self, name, limit=20):
            return foods

    class Cache:
        def __init__(self):
            self.values = {}

        async def get_catalog_resolution(self, key):
            return self.values.get(key)

        async def set_catalog_resolution(self, key, value):
            self.values[key] = value

    selector = AsyncMock()
    selector.signature = "selector-v1"
    selector.min_confidence = 0.9
    selector.choose.side_effect = [None, ("raw", 0.99)]
    resolver = CatalogResolver(Reader(), selector, Cache())
    query = CatalogQuery(food_name="Arroz", instructions="Pesar antes de añadir al agua.")
    assert (await resolver.resolve(query)).status == "ambiguous"
    recovered = await resolver.resolve(query)
    assert recovered.status == "matched"
    assert recovered.food.id == "raw"
    assert selector.choose.await_count == 2
