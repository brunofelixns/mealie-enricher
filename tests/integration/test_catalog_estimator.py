import json
from unittest.mock import AsyncMock

import pytest

from mealie_enricher.catalog.models import CatalogFood, CatalogResolution
from mealie_enricher.models import MealieRecipe, NutrientSet
from mealie_enricher.services.estimator import (
    Estimator,
    build_nutrition_patch,
    compute_ingredient_hash,
)


def recipe(note="en crudo"):
    return MealieRecipe.model_validate(
        {
            "slug": "arroz",
            "name": "Arroz",
            "recipeServings": 2,
            "recipeInstructions": [{"text": "Cocer el arroz"}],
            "recipeIngredient": [
                {
                    "quantity": 200,
                    "unit": {"name": "g"},
                    "food": {"name": "Arroz"},
                    "note": note,
                }
            ],
        }
    )


async def test_catalog_nutrients_are_scaled_in_python_before_off_or_llm():
    off, llm, resolver = AsyncMock(), AsyncMock(), AsyncMock()
    resolver.resolve.return_value = CatalogResolution(
        status="matched",
        method="rules",
        reason="explicit_state",
        food=CatalogFood(
            id="bedca:1",
            source="bedca",
            source_id="1",
            name="Arroz crudo",
            state="raw",
            nutrients=NutrientSet(kcal_per100g=350, protein_per100g=7),
        ),
    )
    resolver.signature = "catalog:v1"
    result = await Estimator(off, llm, catalog=resolver).estimate_recipe(recipe())
    assert result.total_nutrients.kcal_per100g == 700
    assert result.per_serving_nutrients.kcal_per100g == 350
    assert result.per_serving_nutrients.fat_per100g is None
    off.lookup_nutrients.assert_not_called()
    llm.estimate_nutrients.assert_not_called()
    query = resolver.resolve.call_args.args[0]
    assert query.note == "en crudo"
    assert query.instructions == "Cocer el arroz"
    trace = json.loads(build_nutrition_patch(result, "hash").extras["calorie_estimator_catalog"])
    assert trace[0]["id"] == "bedca:1"


async def test_ambiguous_food_does_not_fall_back_to_an_unrelated_product():
    off, llm, resolver = AsyncMock(), AsyncMock(), AsyncMock()
    resolver.resolve.return_value = CatalogResolution(status="ambiguous", reason="needs_context")
    resolver.signature = "catalog:v1"
    result = await Estimator(off, llm, catalog=resolver).estimate_recipe(recipe(note=""))
    assert result.unmatched_ingredients == ["Arroz"]
    assert result.total_nutrients.kcal_per100g is None
    off.lookup_nutrients.assert_not_called()
    llm.estimate_nutrients.assert_not_called()
    patch = build_nutrition_patch(result, "new-hash")
    assert "calories" in patch.nutrition
    assert patch.nutrition["calories"] is None
    assert patch.extras["calorie_estimator_total_kcal"] == ""


def test_catalog_hash_changes_with_context_or_version_only_when_enabled():
    raw, cooked = recipe(), recipe("ya cocido")
    assert compute_ingredient_hash(raw) == compute_ingredient_hash(cooked)
    assert compute_ingredient_hash(raw, "v1") != compute_ingredient_hash(cooked, "v1")
    assert compute_ingredient_hash(raw, "v1") != compute_ingredient_hash(raw, "v2")


@pytest.mark.parametrize("unit, expected", [("ml", None), ("gramos", 200)])
async def test_catalog_does_not_assume_volume_equals_mass(unit, expected):
    off, llm, resolver = AsyncMock(), AsyncMock(), AsyncMock()
    llm.estimate_grams.return_value = None
    resolver.signature = "v1"
    resolver.resolve.return_value = CatalogResolution(
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
    value = recipe()
    value.recipe_ingredient[0].unit.name = unit
    result = await Estimator(off, llm, catalog=resolver).estimate_recipe(value)
    assert result.matched_ingredients[0].grams == expected
    assert result.matched_count == (0 if expected is None else 1)


async def test_catalog_mode_clears_previous_values_even_without_ingredient_traces():
    off, llm, resolver = AsyncMock(), AsyncMock(), AsyncMock()
    resolver.signature = "v1"
    empty = MealieRecipe(slug="empty", recipeIngredient=[])
    result = await Estimator(off, llm, catalog=resolver).estimate_recipe(empty)
    patch = build_nutrition_patch(result, "hash", catalog_mode=True)
    assert patch.nutrition["calories"] is None
    assert patch.extras["calorie_estimator_total_kcal"] == ""
    assert patch.extras["calorie_estimator_catalog"] == "[]"
