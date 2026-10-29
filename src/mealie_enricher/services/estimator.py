import asyncio
import hashlib

from ..clients.open_food_facts import OffClient
from ..compat import js_number, js_number_str, js_round, js_string, json_stringify
from ..config import EstimateSettings
from ..models import (
    EstimateResult,
    IngredientMatch,
    IngredientOutcome,
    MealieIngredient,
    MealieRecipe,
    NutrientSet,
    NutritionPatch,
)
from .llm_estimator import LlmEstimator
from .unit_converter import convert_to_grams

NUTRITION_FIELDS = {
    "kcal_per100g": "calories",
    "protein_per100g": "proteinContent",
    "carbs_per100g": "carbohydrateContent",
    "fat_per100g": "fatContent",
    "saturated_fat_per100g": "saturatedFatContent",
    "trans_fat_per100g": "transFatContent",
    "unsaturated_fat_per100g": "unsaturatedFatContent",
    "fiber_per100g": "fiberContent",
    "sugar_per100g": "sugarContent",
    "sodium_per100g": "sodiumContent",
    "cholesterol_per100g": "cholesterolContent",
}


class Estimator:
    def __init__(self, off: OffClient, llm: LlmEstimator) -> None:
        self.off, self.llm = off, llm

    async def _evaluate(self, ingredient: MealieIngredient) -> IngredientOutcome | None:
        name = ingredient.food.name if ingredient.food else None
        quantity = js_number(ingredient.quantity)
        if not name or ingredient.quantity is None or quantity <= 0:
            return None
        grams = convert_to_grams(quantity, ingredient.unit)
        estimated = False
        if grams is None and ingredient.unit and ingredient.unit.name:
            grams = await self.llm.estimate_grams(quantity, ingredient.unit.name, name)
            estimated = grams is not None
        if grams is None:
            return IngredientOutcome(
                food_name=name, grams=None, nutrients=None, llm_estimated=False
            )
        match = await self.off.lookup_nutrients(
            name, ingredient.unit.name if ingredient.unit else None
        )
        if not match.matched or match.nutrients is None:
            nutrients = await self.llm.estimate_nutrients(name)
            return IngredientOutcome(
                food_name=name,
                grams=grams,
                nutrients=nutrients,
                llm_estimated=nutrients is not None,
            )
        return IngredientOutcome(
            food_name=name, grams=grams, nutrients=match.nutrients, llm_estimated=estimated
        )

    async def estimate_recipe(self, recipe: MealieRecipe) -> EstimateResult:
        outcomes = await asyncio.gather(
            *(self._evaluate(item) for item in recipe.recipe_ingredient)
        )
        return aggregate_ingredients(recipe, list(outcomes))


def compute_ingredient_hash(recipe: MealieRecipe) -> str:
    parts = [
        "|".join(
            [
                js_string(ingredient.quantity if ingredient.quantity is not None else 0),
                ingredient.unit.name if ingredient.unit else "",
                ingredient.food.name if ingredient.food else "",
            ]
        )
        for ingredient in recipe.recipe_ingredient
    ]
    parts.sort(key=lambda part: part.encode("utf-16-be", errors="surrogatepass"))
    for name, val in [
        ("servings", recipe.recipe_servings),
        ("yieldQuantity", recipe.recipe_yield_quantity),
    ]:
        parts.append(name + ":" + (js_string(val) if val is not None else ""))
    return hashlib.sha256(",".join(parts).encode("utf-8", errors="replace")).hexdigest()


def should_estimate(recipe: MealieRecipe, settings: EstimateSettings) -> bool:
    if settings.strategy == "all":
        return True
    tag = settings.tag.lower()
    return any(item.slug == tag or item.name.lower() == tag for item in recipe.tags or [])


def has_manual_calories(recipe: MealieRecipe) -> bool:
    has_hash = (recipe.extras or {}).get("calorie_estimator_hash") is not None
    calories = recipe.nutrition.calories if recipe.nutrition else None
    return not has_hash and calories is not None and bool(calories.strip())


def build_manual_ack_patch(recipe: MealieRecipe, ingredient_hash: str) -> NutritionPatch:
    return NutritionPatch(
        extras={
            **(recipe.extras or {}),
            "calorie_estimator_hash": ingredient_hash,
            "calorie_estimator_unmatched": "[]",
            "calorie_estimator_note": "Manual — preserved existing calorie entry",
        }
    )


def aggregate_ingredients(
    recipe: MealieRecipe, outcomes: list[IngredientOutcome | None]
) -> EstimateResult:
    totals: dict[str, float | None] = dict.fromkeys(NUTRITION_FIELDS, None)
    matches: list[IngredientMatch] = []
    unmatched: list[str] = []
    for outcome in outcomes:
        if outcome is None:
            continue
        if outcome.grams is None or outcome.nutrients is None:
            unmatched.append(outcome.food_name)
            matches.append(
                IngredientMatch(
                    name=outcome.food_name, grams=outcome.grams, matched=False, nutrients=None
                )
            )
            continue
        factor = outcome.grams / 100
        for key in totals:
            current = totals[key]
            value = getattr(outcome.nutrients, key)
            totals[key] = (
                None
                if current is None and value is None
                else (current or 0) + (value or 0) * factor
            )
        matches.append(
            IngredientMatch(
                name=outcome.food_name,
                grams=outcome.grams,
                matched=True,
                nutrients=outcome.nutrients,
                llm_estimated=outcome.llm_estimated,
            )
        )
    servings = recipe.recipe_servings
    if servings is None:
        servings = recipe.recipe_yield_quantity
    if servings is None:
        servings = 1
    numeric_servings = js_number(servings)
    per_serving = {
        key: js_round(value / numeric_servings)
        if value is not None and numeric_servings > 0
        else None
        for key, value in totals.items()
    }
    return EstimateResult(
        slug=recipe.slug,
        servings=servings,
        total_nutrients=NutrientSet(**totals),
        per_serving_nutrients=NutrientSet(**per_serving),
        matched_count=sum(match.matched for match in matches),
        unmatched_count=len(unmatched),
        unmatched_ingredients=unmatched,
        matched_ingredients=matches,
    )


def build_nutrition_patch(result: EstimateResult, ingredient_hash: str) -> NutritionPatch:
    extras = {
        "calorie_estimator_hash": ingredient_hash,
        "calorie_estimator_unmatched": json_stringify(result.unmatched_ingredients),
    }
    llm_names = [item.name for item in result.matched_ingredients if item.llm_estimated]
    if llm_names:
        extras["calorie_estimator_llm_ingredients"] = json_stringify(llm_names)
    total_kcal = result.total_nutrients.kcal_per100g
    if total_kcal is not None and total_kcal > 0:
        extras["calorie_estimator_total_kcal"] = js_number_str(total_kcal)
    if result.servings is not None:
        extras["calorie_estimator_yield"] = js_string(result.servings)
    nutrition = {}
    for key, external in NUTRITION_FIELDS.items():
        value = getattr(result.per_serving_nutrients, key)
        if value is not None:
            nutrition[external] = js_number_str(value)
    return NutritionPatch(nutrition=nutrition, extras=extras)
