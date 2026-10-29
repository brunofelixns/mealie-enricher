import logging

from ..clients.mealie import MealieClient, get_recipe_household_id
from ..compat import js_number_str, json_stringify
from ..config import Settings
from ..models import ExecutionEstimate, ExecutionHandle, ExecutionTrigger, MealieRecipePatch
from ..runtime.slug_queue import SlugQueue
from ..storage.history import ExecutionHistory
from .estimator import (
    build_manual_ack_patch,
    compute_ingredient_hash,
    has_manual_calories,
    should_estimate,
)
from .tagging import TaggingService, per_serving_from_recipe_nutrition, tags_are_complete

logger = logging.getLogger(__name__)


class ProcessingService:
    def __init__(
        self,
        settings: Settings,
        mealie: MealieClient,
        tagging: TaggingService,
        queue: SlugQueue,
        history: ExecutionHistory,
    ) -> None:
        self.settings, self.mealie, self.tagging = settings, mealie, tagging
        self.queue, self.history = queue, history

    async def _process(
        self, slug: str, trigger: ExecutionTrigger, handle: ExecutionHandle | None = None
    ) -> None:
        handle = handle or self.history.record_start(trigger, slug)
        try:
            recipe = await self.mealie.get_recipe(slug)
            household_id = get_recipe_household_id(recipe)
            handle.set_recipe(recipe.name, household_id)
            if not should_estimate(recipe, self.settings.estimate):
                handle.complete("filtered", ["Recipe not tagged for estimation"])
                return
            ingredient_hash = compute_ingredient_hash(recipe)
            if trigger != "estimate":
                if (recipe.extras or {}).get("calorie_estimator_hash") == ingredient_hash:
                    if tags_are_complete(recipe):
                        handle.complete("skipped", ["Ingredients unchanged, tags already applied"])
                        return
                    nutrients = per_serving_from_recipe_nutrition(recipe.nutrition)
                    tags, slugs = await self.tagging.resolve_and_merge_tags(
                        recipe, nutrients, household_id
                    )
                    await self.mealie.patch_recipe(
                        slug,
                        MealieRecipePatch(
                            tags=tags,
                            extras={
                                **(recipe.extras or {}),
                                "calorie_estimator_tags": json_stringify(slugs),
                            },
                        ),
                        household_id,
                    )
                    handle.complete("tags-added", ["Added auto-tags: " + ", ".join(slugs)])
                    return
                if has_manual_calories(recipe):
                    patch = build_manual_ack_patch(recipe, ingredient_hash)
                    await self.mealie.patch_recipe(
                        slug,
                        MealieRecipePatch.model_validate(
                            patch.model_dump(by_alias=True, exclude_unset=True)
                        ),
                        household_id,
                    )
                    calories = recipe.nutrition.calories if recipe.nutrition else "?"
                    handle.complete("manual", [f"Preserved manual calories: {calories} kcal"])
                    return
            result = await self.tagging.estimate_and_tag(recipe, ingredient_hash, household_id)
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
