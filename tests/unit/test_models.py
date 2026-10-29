from mealie_enricher.models import MealieRecipe, NutrientSet
from tests.parity.cases import load_case


def test_recipe_round_trip_preserves_aliases_and_foreign_extras():
    data = load_case("hash-basic")["input"]
    recipe = MealieRecipe.model_validate(data)
    assert recipe.recipe_servings == 2
    assert recipe.model_dump(by_alias=True, exclude_unset=True) == data


def test_unknown_nutrients_stay_null():
    assert all(value is None for value in NutrientSet().model_dump().values())
