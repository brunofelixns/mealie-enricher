import json
import logging
import math

from ..agents.nova_decisions import NOVA_EXTRA, NovaAssessment, OpenAINovaClassifier
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

logger = logging.getLogger(__name__)

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
    auto_slugs = {tag.slug for tag in auto_tags}
    return [
        tag for tag in recipe.tags or [] if tag.slug not in old_slugs and tag.slug not in auto_slugs
    ] + auto_tags


def tags_are_complete(recipe: MealieRecipe) -> bool:
    slugs = json.loads((recipe.extras or {}).get("calorie_estimator_tags") or "[]")
    current = {tag.slug for tag in recipe.tags or []}
    legacy_auto_tags = any(
        tag.slug in slugs and tag.name in LEGACY_AUTO_TAG_NAMES for tag in recipe.tags or []
    )
    return bool(slugs) and all(slug in current for slug in slugs) and not legacy_auto_tags


class TaggingService:
    def __init__(
        self,
        mealie: MealieClient,
        estimator: Estimator,
        nova: OpenAINovaClassifier | None = None,
    ) -> None:
        self.mealie, self.estimator = mealie, estimator
        self.nova = nova

    def tags_are_complete(self, recipe: MealieRecipe) -> bool:
        result = self.nova.cached(recipe) if self.nova is not None else None
        if result is not None and result.tag_status == "unavailable":
            # The assessment was saved, but Mealie could not resolve the tag.
            # Do not generate another patch on our own webhook; force/context changes retry.
            return self.nutrition_tags_are_complete(recipe)
        if not tags_are_complete(recipe):
            return False
        if self.nova is None:
            return True
        owned = json.loads((recipe.extras or {}).get("calorie_estimator_tags") or "[]")
        return result is not None and any(
            tag.name == result.tag and tag.slug == result.tag_slug and tag.slug in owned
            for tag in recipe.tags or []
        )

    def nutrition_tags_are_complete(self, recipe: MealieRecipe) -> bool:
        """Allow NOVA-only updates to retain existing, possibly partial nutrition."""
        owned = json.loads((recipe.extras or {}).get("calorie_estimator_tags") or "[]")
        nova_slug = None
        try:
            previous = NovaAssessment.model_validate_json((recipe.extras or {}).get(NOVA_EXTRA, ""))
            nova_slug = previous.tag_slug
        except ValueError, TypeError:
            pass
        current = {tag.slug: tag for tag in recipe.tags or []}
        return all(
            slug in current and current[slug].name not in LEGACY_AUTO_TAG_NAMES
            for slug in owned
            if slug != nova_slug
        )

    async def build_tags_patch(
        self,
        recipe: MealieRecipe,
        nutrients: NutrientSet | None,
        household_id: str | None,
        *,
        force_nova: bool = False,
    ) -> MealieRecipePatch:
        names = compute_tags(nutrients) if nutrients is not None else []
        old_slugs = json.loads((recipe.extras or {}).get("calorie_estimator_tags") or "[]")
        retained_slugs: list[str] = []
        if nutrients is None:
            # A manual or unchanged nutrition entry only needs its NOVA tag refreshed.
            nova_names = {"NOVA:1", "NOVA:2", "NOVA:3", "NOVA:4", "NOVA:Desconocida"}
            remove = {tag.slug for tag in recipe.tags or [] if tag.name in nova_names}
            try:
                previous = NovaAssessment.model_validate_json(
                    (recipe.extras or {}).get(NOVA_EXTRA, "")
                )
                if previous.tag_slug:
                    remove.add(previous.tag_slug)
            except ValueError, TypeError:
                pass
            retained_slugs = [slug for slug in old_slugs if slug not in remove]
            old_slugs = [slug for slug in old_slugs if slug in remove]
        result = await self.nova.classify(recipe, force=force_nova) if self.nova else None
        if result is not None:
            names.append(result.tag)
        auto_tags = await self.mealie.get_or_create_tags(names, household_id)
        extras = dict(recipe.extras or {})
        if result is not None:
            nova_tag = next((tag for tag in auto_tags if tag.name == result.tag), None)
            result = result.model_copy(
                update={
                    "tag_slug": nova_tag.slug if nova_tag is not None else None,
                    "tag_status": "applied" if nova_tag is not None else "unavailable",
                }
            )
            if nova_tag is None:
                logger.warning("NOVA tag unavailable; assessment saved without tag ownership")
            extras[NOVA_EXTRA] = result.model_dump_json()
        extras["calorie_estimator_tags"] = json_stringify(
            retained_slugs + [tag.slug for tag in auto_tags]
        )
        return MealieRecipePatch(tags=merge_tags(recipe, auto_tags, old_slugs), extras=extras)

    async def estimate_and_tag(
        self,
        recipe: MealieRecipe,
        ingredient_hash: str,
        household_id: str | None,
        *,
        force_nova: bool = False,
    ) -> EstimateAndTagResult:
        result = await self.estimator.estimate_recipe(recipe)
        patch = build_nutrition_patch(
            result,
            ingredient_hash,
            catalog_mode=self.estimator.catalog is not None,
        )
        if "calorie_estimator_catalog" in (recipe.extras or {}) and (
            "calorie_estimator_catalog" not in patch.extras
        ):
            patch.extras["calorie_estimator_catalog"] = "[]"
        if "calorie_estimator_ingredient_recovery" in (recipe.extras or {}) and (
            "calorie_estimator_ingredient_recovery" not in patch.extras
        ):
            patch.extras["calorie_estimator_ingredient_recovery"] = "[]"
        tag_patch = await self.build_tags_patch(
            recipe, result.per_serving_nutrients, household_id, force_nova=force_nova
        )
        slugs = json.loads((tag_patch.extras or {})["calorie_estimator_tags"])
        await self.mealie.patch_recipe(
            recipe.slug,
            MealieRecipePatch(
                nutrition={key: value for key, value in (patch.nutrition or {}).items()},
                tags=tag_patch.tags,
                extras={
                    **(tag_patch.extras or {}),
                    **patch.extras,
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
