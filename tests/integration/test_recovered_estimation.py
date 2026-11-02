import asyncio
import copy
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from mealie_enricher.agents.estimator_agent import AgentLlmRunner
from mealie_enricher.app import create_app
from mealie_enricher.catalog.models import CatalogFood
from mealie_enricher.catalog.resolver import CatalogResolver
from mealie_enricher.config import LlmSettings, OffSettings, load_settings
from mealie_enricher.models import MealieRecipe, NutrientSet
from mealie_enricher.runtime.rate_limiter import RateLimiter
from mealie_enricher.services.estimator import (
    Estimator,
    build_nutrition_patch,
    compute_ingredient_hash,
)
from mealie_enricher.services.llm_estimator import LlmEstimator


class SyntheticCatalog:
    fingerprint = "recovery-test-catalog"

    def search(self, name, limit=20):
        # Deliberately synthetic energy values make the Python scaling checkable.
        foods = {
            "Jamoncitos de pollo": 100,
            "Quinoa": 200,
            "berenjena": 10,
            "tomate": 20,
            "calabacín": 30,
            "aceite de oliva": 900,
            "Agua": 0,
        }
        return (
            [
                CatalogFood(
                    id="test:" + name,
                    source="bedca",
                    source_id=name,
                    name=name,
                    nutrients=NutrientSet(kcal_per100g=foods[name]),
                )
            ]
            if name in foods
            else []
        )


def imported_recipe():
    lines = [
        (8, None, None, "8 unidad(es) Jamoncitos de pollo"),
        (
            100,
            {"name": "gramo", "standardUnit": "gram", "standardQuantity": 1},
            None,
            "100 gramo(s) Quinoa",
        ),
        (1, None, {"name": "berenjena"}, "1 unidad(es) Berenjena"),
        (1, None, {"name": "tomate"}, "1 unidad(es) Tomate"),
        (1, None, {"name": "pimentón ahumado"}, "1 sobre(s) Pimentón ahumado"),
        (1, None, None, "1 sobre(s) Tomillo seco"),
        (1, None, {"name": "calabacín"}, "1 unidad(es) Calabacín"),
        (1, {"name": "pizca"}, None, "1 pizca(s) Sal y pimienta"),
        (
            2,
            {"name": "cucharada", "standardQuantity": 0.5, "standardUnit": "fluid_ounce"},
            {"name": "aceite de oliva"},
            "2 cucharada(s) Aceite de oliva",
        ),
        (
            600,
            {"name": "mililitro", "standardQuantity": 1, "standardUnit": "milliliter"},
            None,
            "600 mililitro(s) Agua",
        ),
    ]
    return MealieRecipe(
        slug="jamoncitos-de-pollo-al-estilo-mediterraneo-guisados-con-verduras-y-quinoa",
        name="Jamoncitos de pollo con verduras y quinoa",
        recipe_servings=2,
        recipe_ingredient=[
            {
                "quantity": qty,
                "unit": unit,
                "food": food,
                "originalText": text,
                "referenceId": f"line-{index}",
            }
            for index, (qty, unit, food, text) in enumerate(lines)
        ],
    )


async def test_imported_recipe_recovers_sources_and_keeps_unknown_packages_pending(cache):
    recipe = imported_recipe()
    before = recipe.model_dump()
    off, llm = AsyncMock(), AsyncMock()
    off.lookup_nutrients.return_value.matched = False
    llm.estimate_nutrients.return_value = None
    weights = {
        "Jamoncitos de pollo": 100,
        "Berenjena": 300,
        "Tomate": 150,
        "Calabacín": 200,
        "Sal y pimienta": 0.5,
        "Agua": 1,
    }

    async def weight(qty, unit, food):
        return qty * weights[food]

    llm.estimate_recovered_grams.side_effect = weight
    llm.estimate_grams.return_value = 28
    # The supplied recipe already resolves this fully structured ingredient through Decisions.
    selector = AsyncMock(signature="synthetic-decisions", min_confidence=0.9)
    selector.choose.return_value = ("test:aceite de oliva", 1.0)
    estimator = Estimator(off, llm, catalog=CatalogResolver(SyntheticCatalog(), selector, cache))
    result = await estimator.estimate_recipe(recipe)
    assert recipe.model_dump() == before
    assert result.matched_count == 7, [
        (item.name, item.grams, item.matched, (item.model_extra or {}).get("catalog"))
        for item in result.matched_ingredients
    ]
    assert result.unmatched_count == 3
    assert set(result.unmatched_ingredients) == {
        "pimentón ahumado",
        "Tomillo seco",
        "Sal y pimienta",
    }
    assert result.total_nutrients.kcal_per100g == 1372  # 800+200+30+30+60+252+0.
    assert result.per_serving_nutrients.kcal_per100g == 686
    matches = {item.name: item for item in result.matched_ingredients}
    assert matches["Quinoa"].grams == 100
    assert matches["Quinoa"].llm_estimated is False
    assert matches["Jamoncitos de pollo"].grams == 800
    assert matches["Jamoncitos de pollo"].llm_estimated is True
    metadata = json.loads(
        build_nutrition_patch(result, "hash").extras["calorie_estimator_ingredient_recovery"]
    )
    assert len(metadata) == 9  # Olive oil was already fully structured.
    assert next(entry for entry in metadata if entry["food"] == "Sal y pimienta")[
        "weight_estimated"
    ]
    assert {entry["reason"] for entry in metadata if entry["status"] == "pending"} >= {
        "package_weight_unknown"
    }
    assert not any("sobre" in call.args[1] for call in llm.estimate_recovered_grams.call_args_list)


async def test_recovered_mass_uses_catalog_without_llm_and_survives_disabled_fallback(cache):
    off, llm = AsyncMock(), AsyncMock()
    value = MealieRecipe(slug="quinoa", recipe_ingredient=[{"originalText": "100 gramo(s) Quinoa"}])
    result = await Estimator(
        off, llm, catalog=CatalogResolver(SyntheticCatalog(), None, cache)
    ).estimate_recipe(value)
    assert result.total_nutrients.kcal_per100g == 200
    assert result.matched_count == 1
    llm.estimate_recovered_grams.assert_not_called()
    llm.estimate_nutrients.assert_not_called()
    off.lookup_nutrients.assert_not_called()


@pytest.mark.parametrize("enabled", [True, False])
async def test_recovered_volume_never_uses_the_legacy_ml_equals_g_assumption(enabled, cache):
    llm_settings = LlmSettings(enabled=enabled, api_key="synthetic", base_url="https://llm.test")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as http:
        llm = LlmEstimator(
            llm_settings,
            AgentLlmRunner(llm_settings, http),
            cache,
            RateLimiter(OffSettings(), llm_settings),
        )
        off = AsyncMock()
        value = MealieRecipe(
            slug="oil", recipe_ingredient=[{"originalText": "100 ml aceite de oliva"}]
        )
        result = await Estimator(off, llm).estimate_recipe(value)
    assert result.matched_count == 0
    assert result.matched_ingredients[0].grams is None
    off.lookup_nutrients.assert_not_called()


@pytest.mark.parametrize(
    "output,want",
    [
        ("0.5", 1.5),
        ("12.75", 38.25),
        ("80 grams", None),
        ("NaN", None),
        ("Infinity", None),
        ("-2", None),
        ("0", None),
    ],
)
async def test_recovered_weights_use_strict_decimals_and_separate_cache(output, want, cache):
    settings = LlmSettings(enabled=True, api_key="synthetic", rate_limit=10000)
    runner = AsyncMock()
    runner.complete.return_value = output
    llm = LlmEstimator(settings, runner, cache, RateLimiter(OffSettings(), settings))
    await cache.set_grams(
        "pizca", "sal", 9
    )  # An older integer estimate must not leak into recovery.
    assert await llm.estimate_recovered_grams(3, "pizca", "sal") == want
    assert await llm.estimate_recovered_grams(3, "pizca", "sal") == want
    assert runner.complete.call_count == (1 if want is not None else 2)
    assert await cache.get_grams("pizca", "sal") == 9


def test_recovery_hash_includes_original_text_and_invalidates_legacy_incomplete_results():
    first = imported_recipe()
    second = first.model_copy(deep=True)
    second.recipe_ingredient[0].original_text = "8 unidad(es) Pechugas de pollo"
    assert compute_ingredient_hash(first) != compute_ingredient_hash(second)
    assert compute_ingredient_hash(first, "catalog:v1") != compute_ingredient_hash(
        second, "catalog:v1"
    )
    assert compute_ingredient_hash(first) == compute_ingredient_hash(first.model_copy(deep=True))


async def test_processing_only_patches_nutrition_tags_and_metadata(tmp_path):
    value = imported_recipe().model_dump(by_alias=True)
    value["recipeIngredient"] = [value["recipeIngredient"][1]]
    original_lines = copy.deepcopy(value["recipeIngredient"])
    patches = []
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "synthetic",
            "MEALIE_URL": "http://mealie.test",
            "CACHE_DB_PATH": str(tmp_path / "cache.db"),
            "EVENT_DEBOUNCE_MS": "0",
        }
    )

    def respond(request):
        if request.url.host == "search.openfoodfacts.org":
            return httpx.Response(
                200,
                json={
                    "hits": [{"product_name": "Quinoa", "nutriments": {"energy-kcal_100g": 200}}]
                },
            )
        if request.url.path == "/api/organizers/tags":
            name = json.loads(request.content)["name"]
            return httpx.Response(200, json={"id": name, "name": name, "slug": name})
        if request.method == "PATCH":
            patch = json.loads(request.content)
            patches.append(patch)
            value.update(patch)
        return httpx.Response(200, json=value)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as external:
        app = create_app(settings, http=external)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://app.test"
            ) as client:
                assert (
                    await client.post("/estimate", json={"content": {"slug": value["slug"]}})
                ).status_code == 202
                while app.state.tasks.pending:
                    await asyncio.gather(*list(app.state.tasks.pending))
                assert patches[-1]["nutrition"]["calories"] == "100"
                assert set(patches[-1]) <= {"nutrition", "tags", "extras"}
                assert value["recipeIngredient"] == original_lines
                metadata = json.loads(
                    patches[-1]["extras"]["calorie_estimator_ingredient_recovery"]
                )
                assert metadata[0]["food"] == "Quinoa"
                await app.state.processing.process_webhook(value["slug"])
                assert len(patches) == 1  # The enricher's own PATCH does not cause an update loop.
                # A later repair in Mealie supersedes, and clears, the internal recovery view.
                value["recipeIngredient"][0]["food"] = {"name": "Quinoa"}
                repaired_lines = copy.deepcopy(value["recipeIngredient"])
                await app.state.processing.process_webhook(value["slug"])
                assert len(patches) == 2
                assert patches[-1]["extras"]["calorie_estimator_ingredient_recovery"] == "[]"
                assert value["recipeIngredient"] == repaired_lines
                value["recipeIngredient"] = [{"originalText": "sal al gusto"}]
                value["extras"]["calorie_estimator_llm_ingredients"] = '["old estimate"]'
                await app.state.processing.process_webhook(value["slug"])
                assert patches[-1]["nutrition"]["calories"] is None
                assert patches[-1]["extras"]["calorie_estimator_total_kcal"] == ""
                assert patches[-1]["extras"]["calorie_estimator_llm_ingredients"] == "[]"
