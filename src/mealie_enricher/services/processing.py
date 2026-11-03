import json
import logging
from typing import TYPE_CHECKING

from ..clients.mealie import MealieClient, get_recipe_household_id
from ..compat import js_number_str
from ..config import Settings
from ..models import ExecutionEstimate, ExecutionHandle, ExecutionTrigger, MealieRecipePatch
from ..runtime.slug_queue import SlugQueue
from ..storage.history import ExecutionHistory
from .estimator import (
    build_manual_ack_patch,
    has_manual_calories,
    should_estimate,
)
from .tagging import TaggingService, per_serving_from_recipe_nutrition

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..pricing.service import PricingService


class ProcessingService:
    def __init__(
        self,
        settings: Settings,
        mealie: MealieClient,
        tagging: TaggingService,
        queue: SlugQueue,
        history: ExecutionHistory,
        pricing: "PricingService | None" = None,
    ) -> None:
        self.settings, self.mealie, self.tagging = settings, mealie, tagging
        self.queue, self.history = queue, history
        self.pricing = pricing

    async def _process(
        self, slug: str, trigger: ExecutionTrigger, handle: ExecutionHandle | None = None
    ) -> None:
        handle = handle or self.history.record_start(trigger, slug)
        recipe_loaded = False
        try:
            await self.history.flush()
            recipe = await self.mealie.get_recipe(slug)
            recipe_loaded = True
            household_id = get_recipe_household_id(recipe)
            handle.set_recipe(recipe.name, household_id)
            await self.history.flush()
            if not should_estimate(recipe, self.settings.estimate):
                handle.complete("filtered", ["Recipe not tagged for estimation"])
                return
            ingredient_hash = self.tagging.estimator.ingredient_hash(recipe)
            if trigger != "estimate":
                if (recipe.extras or {}).get("calorie_estimator_hash") == ingredient_hash:
                    if self.tagging.tags_are_complete(recipe):
                        handle.complete("skipped", ["Ingredients unchanged, tags already applied"])
                        return
                    nova_only = (
                        self.tagging.nova is not None
                        and self.tagging.nutrition_tags_are_complete(recipe)
                    )
                    nutrients = (
                        None if nova_only else per_serving_from_recipe_nutrition(recipe.nutrition)
                    )
                    tag_patch = await self.tagging.build_tags_patch(recipe, nutrients, household_id)
                    await self.mealie.patch_recipe(
                        slug,
                        tag_patch,
                        household_id,
                    )
                    slugs = json.loads((tag_patch.extras or {})["calorie_estimator_tags"])
                    handle.complete("tags-added", ["Added auto-tags: " + ", ".join(slugs)])
                    return
                if has_manual_calories(recipe):
                    patch = build_manual_ack_patch(recipe, ingredient_hash)
                    manual_patch = MealieRecipePatch.model_validate(
                        patch.model_dump(by_alias=True, exclude_unset=True)
                    )
                    if self.tagging.nova is not None:
                        tag_patch = await self.tagging.build_tags_patch(recipe, None, household_id)
                        manual_patch.tags = tag_patch.tags
                        tag_extras = tag_patch.extras or {}
                        manual_patch.extras = {
                            **patch.extras,
                            "calorie_estimator_tags": tag_extras["calorie_estimator_tags"],
                            "calorie_estimator_nova": tag_extras["calorie_estimator_nova"],
                        }
                    await self.mealie.patch_recipe(
                        slug,
                        manual_patch,
                        household_id,
                    )
                    calories = recipe.nutrition.calories if recipe.nutrition else "?"
                    handle.complete("manual", [f"Preserved manual calories: {calories} kcal"])
                    return
            result = await self.tagging.estimate_and_tag(
                recipe, ingredient_hash, household_id, force_nova=trigger == "estimate"
            )
            calories = js_number_str(result.calories) if result.calories is not None else "?"
            handle.complete(
                "processed",
                [
                    f"Set calories: {calories} kcal/serving",
                    "Auto-tags: " + ", ".join(result.tag_slugs),
                ],
                ExecutionEstimate(
                    nutrients=result.per_serving_nutrients,
                    matched_count=result.matched_count,
                    unmatched_count=result.unmatched_count,
                ),
            )
        except Exception as error:
            handle.fail(error)
            logger.error("%s background processing failed: %s", trigger, error)
        finally:
            if self.pricing is not None and recipe_loaded:
                try:
                    await self.pricing.process_slug(slug)
                except Exception as error:
                    logger.warning(
                        "Independent recipe pricing failed type=%s", type(error).__name__
                    )
            await self.history.flush()

    async def process_webhook(self, slug: str) -> None:
        await self._process(slug, "webhook")

    async def process_estimate(self, slug: str) -> None:
        await self._process(slug, "estimate")

    async def process_backfill(self) -> None:
        try:
            slugs = await self.mealie.get_all_recipes()
            for index, slug in enumerate(slugs, 1):
                handle = self.history.record_start("backfill", slug)

                async def process(slug: str = slug, handle: ExecutionHandle = handle) -> None:
                    await self._process(slug, "backfill", handle)

                await self.queue.run_now(slug, process)
                if index % 10 == 0:
                    logger.info("Backfill progress: %s/%s", index, len(slugs))
        except Exception as error:
            logger.error("Backfill background processing failed: %s", error)
