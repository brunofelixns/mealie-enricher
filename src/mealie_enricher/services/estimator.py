import asyncio
import hashlib
import json
from typing import TYPE_CHECKING, Any

from ..catalog.models import CatalogQuery
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
from .unit_converter import convert_catalog_mass, convert_to_grams

if TYPE_CHECKING:
    from ..catalog.resolver import CatalogResolver

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
    def __init__(
        self,
        off: OffClient,
        llm: LlmEstimator,
        *,
        catalog: CatalogResolver | None = None,
    ) -> None:
        self.off, self.llm = off, llm
        self.catalog = catalog

    def ingredient_hash(self, recipe: MealieRecipe) -> str:
        return compute_ingredient_hash(recipe, self.catalog.signature if self.catalog else None)

    async def _evaluate(
        self,
        ingredient: MealieIngredient,
        recipe: MealieRecipe,
    ) -> IngredientOutcome | None:
        name = ingredient.food.name if ingredient.food else None
        quantity = js_number(ingredient.quantity)
        if not name or ingredient.quantity is None or quantity <= 0:
            return None
        grams = convert_to_grams(quantity, ingredient.unit)
        resolution = None
        trace: dict[str, Any] | None = None
        if self.catalog is not None:
            resolution = await self.catalog.resolve(ingredient_query(ingredient, recipe))
            if resolution.status != "not_found":
                grams = convert_catalog_mass(quantity, ingredient.unit)
            trace = {
                "name": name,
                "status": resolution.status,
                "reason": resolution.reason,
                "method": resolution.method,
                "catalog_version": self.catalog.signature,
            }
            if resolution.food is not None:
                trace.update(
                    {
                        "id": resolution.food.id,
                        "source": resolution.food.source,
                        "food": resolution.food.name,
                        "state": resolution.food.state,
                        "confidence": resolution.confidence,
                    }
                )
            if resolution.status == "ambiguous":
                return IngredientOutcome(
                    food_name=name,
                    grams=grams,
                    nutrients=None,
                    catalog=trace,
                )
        estimated = False
        if grams is None and ingredient.unit and ingredient.unit.name:
            weight_food = resolution.food.name if resolution and resolution.food else name
            grams = await self.llm.estimate_grams(quantity, ingredient.unit.name, weight_food)
            estimated = grams is not None
        if grams is None:
            return IngredientOutcome(
                food_name=name,
                grams=None,
                nutrients=None,
                llm_estimated=False,
                catalog=trace,
            )
        if resolution is not None and resolution.status == "matched":
            assert resolution.food is not None
            return IngredientOutcome(
                food_name=name,
                grams=grams,
                nutrients=resolution.food.nutrients,
                llm_estimated=estimated,
                catalog=trace,
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
                catalog=trace,
            )
        return IngredientOutcome(
            food_name=name,
            grams=grams,
            nutrients=match.nutrients,
            llm_estimated=estimated,
            catalog=trace,
        )

    async def estimate_recipe(self, recipe: MealieRecipe) -> EstimateResult:
        outcomes = await asyncio.gather(
            *(self._evaluate(item, recipe) for item in recipe.recipe_ingredient)
        )
        return aggregate_ingredients(recipe, list(outcomes))


def ingredient_query(ingredient: MealieIngredient, recipe: MealieRecipe) -> CatalogQuery:
    instructions = (recipe.model_extra or {}).get("recipeInstructions", [])
    text = (
        "\n".join(
            item.get("text", "")
            for item in instructions
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
        if isinstance(instructions, list)
        else ""
    )
    return CatalogQuery(
        food_name=ingredient.food.name if ingredient.food else "",
        quantity=ingredient.quantity,
        unit=ingredient.unit.name if ingredient.unit else "",
        note=ingredient.note or "",
        original_text=ingredient.original_text or ingredient.display,
        recipe_name=recipe.name,
        instructions=text,
    )


def compute_ingredient_hash(recipe: MealieRecipe, catalog_signature: str | None = None) -> str:
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
    if catalog_signature is not None:
        context = {
            "catalog": catalog_signature,
            "ingredients": [
                {
                    "query": ingredient_query(item, recipe).model_dump(),
                    "unit": item.unit.model_dump() if item.unit else None,
                }
                for item in recipe.recipe_ingredient
            ],
        }
        parts.append(json.dumps(context, sort_keys=True, ensure_ascii=False))
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
        trace_values: dict[str, Any] = {"catalog": outcome.catalog} if outcome.catalog else {}
        if outcome.grams is None or outcome.nutrients is None:
            unmatched.append(outcome.food_name)
            matches.append(
                IngredientMatch(
                    name=outcome.food_name,
                    grams=outcome.grams,
                    matched=False,
                    nutrients=None,
                    **trace_values,
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
                **trace_values,
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


def build_nutrition_patch(
    result: EstimateResult,
    ingredient_hash: str,
    *,
    catalog_mode: bool = False,
) -> NutritionPatch:
    extras = {
        "calorie_estimator_hash": ingredient_hash,
        "calorie_estimator_unmatched": json_stringify(result.unmatched_ingredients),
    }
    llm_names = [item.name for item in result.matched_ingredients if item.llm_estimated]
    catalog_traces = [
        item.model_extra["catalog"]
        for item in result.matched_ingredients
        if item.model_extra and item.model_extra.get("catalog")
    ]
    if catalog_traces or catalog_mode:
        extras["calorie_estimator_catalog"] = json_stringify(catalog_traces)
    if llm_names:
        extras["calorie_estimator_llm_ingredients"] = json_stringify(llm_names)
    total_kcal = result.total_nutrients.kcal_per100g
    if total_kcal is not None and total_kcal > 0:
        extras["calorie_estimator_total_kcal"] = js_number_str(total_kcal)
    if result.servings is not None:
        extras["calorie_estimator_yield"] = js_string(result.servings)
    nutrition: dict[str, str | None] = {}
    for key, external in NUTRITION_FIELDS.items():
        value = getattr(result.per_serving_nutrients, key)
        if value is not None:
            nutrition[external] = js_number_str(value)
        elif catalog_traces or catalog_mode:
            # Missing catalog values must not leave a previous automatic estimate in Mealie.
            nutrition[external] = None
    if (catalog_traces or catalog_mode) and total_kcal is None:
        extras["calorie_estimator_total_kcal"] = ""
    if (catalog_traces or catalog_mode) and not llm_names:
        extras["calorie_estimator_llm_ingredients"] = "[]"
    return NutritionPatch(nutrition=nutrition, extras=extras)
