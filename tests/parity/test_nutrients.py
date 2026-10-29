import pytest

from mealie_enricher.config import EstimateSettings
from mealie_enricher.models import EstimateResult, IngredientOutcome, MealieRecipe, NutrientSet
from mealie_enricher.services.estimator import (
    aggregate_ingredients,
    build_manual_ack_patch,
    build_nutrition_patch,
    compute_ingredient_hash,
    has_manual_calories,
    should_estimate,
)
from tests.parity.cases import cases_for

CASES = cases_for("estimator")


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["id"].startswith("manual-")], ids=lambda c: c["id"]
)
def test_manual_acknowledgement_preserves_reference(case):
    recipe = MealieRecipe.model_validate(case["input"])
    assert has_manual_calories(recipe) == case["expected_result"]["manual"]
    patch = build_manual_ack_patch(recipe, compute_ingredient_hash(recipe))
    assert patch.model_dump(by_alias=True, exclude_unset=True) == case["expected_result"]["patch"]


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["id"].startswith("strategy-")], ids=lambda c: c["id"]
)
def test_tag_filter_keeps_original_comparisons(case):
    assert (
        should_estimate(
            MealieRecipe.model_validate(case["input"]), EstimateSettings(strategy="tagged")
        )
        == case["expected_result"]
    )


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["id"].startswith("estimate-")], ids=lambda c: c["id"]
)
def test_nutrition_patch_preserves_reference_fields(case):
    result = EstimateResult.model_validate(case["expected_result"]["result"])
    recipe = MealieRecipe.model_validate(case["input"])
    actual = build_nutrition_patch(result, compute_ingredient_hash(recipe))
    assert actual.model_dump(by_alias=True, exclude_unset=True) == case["expected_result"]["patch"]


def test_aggregation_rounds_half_up_and_keeps_unknown_nutrients():
    recipe = MealieRecipe(slug="test", recipeServings=2)
    outcomes = [
        IngredientOutcome(foodName="rice", grams=100, nutrients=NutrientSet(kcalPer100g=101)),
        IngredientOutcome(foodName="unknown", grams=None, nutrients=None),
    ]
    result = aggregate_ingredients(recipe, outcomes)
    assert result.total_nutrients.kcal_per100g == 101
    assert result.per_serving_nutrients.kcal_per100g == 51
    assert result.per_serving_nutrients.protein_per100g is None
    assert result.matched_count == 1
    assert result.unmatched_ingredients == ["unknown"]
