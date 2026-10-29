import json
import math

from ..clients.mealie import MealieClient
from ..compat import js_divide, js_parse_float, json_stringify
from ..models import (
    EstimateAndTagResult,
    MealieNutrition,
    MealieRecipe,
    MealieRecipePatch,
    MealieTag,
    NutrientSet,
)
from .estimator import NUTRITION_FIELDS, Estimator, build_nutrition_patch

LEGACY_AUTO_TAG_NAMES = frozenset(
    {
        "Calories:Light",
        "Calories:Moderate",
        "Calories:Hearty",
        "Calories:Heavy",
        "Digest:Easy",
        "Digest:Moderate",
        "Digest:Slow",
        "Digest:Unknown",
    }
)


def get_calorie_tag(kcal: float | None) -> str | None:
    if kcal is None:
        return None
    if kcal < 350:
        return "Calorías:Bajas"
    if kcal <= 600:
        return "Calorías:Moderadas"
    if kcal <= 850:
        return "Calorías:Altas"
    return "Calorías:Muy altas"


def get_digestibility_tag(nutrients: NutrientSet) -> str:
    kcal, fat = nutrients.kcal_per100g, nutrients.fat_per100g
    if kcal is None or fat is None:
        return "Digestión:Desconocida"
    percentage = js_divide(fat * 9, kcal) * 100
    if percentage < 30 and kcal <= 600:
        return "Digestión:Fácil"
    if percentage >= 40:
        return "Digestión:Lenta"
    return "Digestión:Moderada"


def compute_tags(nutrients: NutrientSet) -> list[str]:
    tag = get_calorie_tag(nutrients.kcal_per100g)
    return ([tag] if tag else []) + [get_digestibility_tag(nutrients)]


def per_serving_from_recipe_nutrition(nutrition: MealieNutrition | None) -> NutrientSet:
    values: dict[str, float | None] = {}
    for key, alias in NUTRITION_FIELDS.items():
        if nutrition is None:
            values[key] = None
            continue
        field = next(
            name for name, info in MealieNutrition.model_fields.items() if info.alias == alias
        )
        if field not in nutrition.model_fields_set:
            raise ValueError("Cannot read properties of undefined (reading 'trim')")
        raw = getattr(nutrition, field)
        parsed = js_parse_float(raw) if raw is not None and raw.strip() else math.nan
        values[key] = None if math.isnan(parsed) else parsed
    return NutrientSet(**values)


def merge_tags(
    recipe: MealieRecipe, auto_tags: list[MealieTag], old_slugs: list[str]
) -> list[MealieTag]:
    return [tag for tag in recipe.tags or [] if tag.slug not in old_slugs] + auto_tags


def tags_are_complete(recipe: MealieRecipe) -> bool:
    slugs = json.loads((recipe.extras or {}).get("calorie_estimator_tags") or "[]")
    current = {tag.slug for tag in recipe.tags or []}
    legacy_auto_tags = any(
        tag.slug in slugs and tag.name in LEGACY_AUTO_TAG_NAMES for tag in recipe.tags or []
    )
    return bool(slugs) and all(slug in current for slug in slugs) and not legacy_auto_tags


class TaggingService:
    def __init__(self, mealie: MealieClient, estimator: Estimator) -> None:
        self.mealie, self.estimator = mealie, estimator

    async def resolve_and_merge_tags(
        self, recipe: MealieRecipe, nutrients: NutrientSet, household_id: str | None
    ) -> tuple[list[MealieTag], list[str]]:
        auto_tags = await self.mealie.get_or_create_tags(compute_tags(nutrients), household_id)
        old_slugs = json.loads((recipe.extras or {}).get("calorie_estimator_tags") or "[]")
        return merge_tags(recipe, auto_tags, old_slugs), [tag.slug for tag in auto_tags]

    async def estimate_and_tag(
        self, recipe: MealieRecipe, ingredient_hash: str, household_id: str | None
    ) -> EstimateAndTagResult:
        result = await self.estimator.estimate_recipe(recipe)
        patch = build_nutrition_patch(result, ingredient_hash)
        tags, slugs = await self.resolve_and_merge_tags(
            recipe, result.per_serving_nutrients, household_id
        )
        await self.mealie.patch_recipe(
            recipe.slug,
            MealieRecipePatch(
                nutrition={key: value for key, value in (patch.nutrition or {}).items()},
                tags=tags,
                extras={
                    **(recipe.extras or {}),
                    **patch.extras,
                    "calorie_estimator_tags": json_stringify(slugs),
                },
            ),
            household_id,
        )
        return EstimateAndTagResult(
            calories=result.per_serving_nutrients.kcal_per100g,
            tag_slugs=slugs,
            per_serving_nutrients=result.per_serving_nutrients,
            matched_count=result.matched_count,
            unmatched_count=result.unmatched_count,
        )
