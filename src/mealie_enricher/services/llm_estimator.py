import json
import logging
import math
import re

from ..agents.estimator_agent import AgentLlmRunner
from ..agents.prompts import (
    build_grams_prompt,
    build_nutrients_prompt,
    build_recovered_grams_prompt,
)
from ..compat import js_number, js_parse_int, js_round
from ..config import LlmSettings
from ..models import NutrientSet
from ..runtime.rate_limiter import RateLimiter
from ..storage.cache import SqliteCache

logger = logging.getLogger(__name__)
KEYS = {
    "kcal_per100g": "kcal",
    "protein_per100g": "protein",
    "carbs_per100g": "carbs",
    "fat_per100g": "fat",
    "saturated_fat_per100g": "saturatedFat",
    "trans_fat_per100g": "transFat",
    "fiber_per100g": "fiber",
    "sugar_per100g": "sugar",
    "sodium_per100g": "sodium",
    "cholesterol_per100g": "cholesterol",
}


class LlmEstimator:
    def __init__(
        self,
        settings: LlmSettings,
        runner: AgentLlmRunner,
        cache: SqliteCache,
        limiter: RateLimiter,
    ) -> None:
        self.settings, self.runner, self.cache, self.limiter = settings, runner, cache, limiter

    async def estimate_grams(self, quantity: float, unit_name: str, food_name: str) -> float | None:
        if not self.settings.enabled or not self.settings.api_key:
            return None
        cached = await self.cache.get_grams(unit_name, food_name)
        if cached is not None:
            return cached * quantity
        try:
            await self.limiter.wait("llm")
            content = await self.runner.complete(
                build_grams_prompt(unit_name, food_name),
                max_tokens=int(self.settings.max_tokens_grams),
            )
            if content is None:
                return None
            value = js_parse_int(content.strip())
            if math.isnan(value) or value <= 0:
                return None
            await self.cache.set_grams(unit_name, food_name, value)
            return value * quantity
        except Exception as error:
            logger.warning("LLM gram estimation failed: %s", error)
            return None

    async def estimate_recovered_grams(
        self, quantity: float, unit_name: str, food_name: str
    ) -> float | None:
        if (
            not self.settings.enabled
            or not self.settings.api_key
            or not math.isfinite(quantity)
            or quantity <= 0
        ):
            return None
        cache_unit = "recovered-weight:v1:" + unit_name
        try:
            cached = await self.cache.get_grams(cache_unit, food_name)
            if cached is not None and math.isfinite(cached) and cached > 0:
                total = cached * quantity
                return total if math.isfinite(total) else None
            await self.limiter.wait("llm")
            content = await self.runner.complete(
                build_recovered_grams_prompt(unit_name, food_name),
                max_tokens=int(self.settings.max_tokens_grams),
            )
            if content is None or not re.fullmatch(r"\+?(?:\d+(?:\.\d*)?|\.\d+)", content.strip()):
                return None
            value = float(content.strip())
            total = value * quantity
            if not math.isfinite(total) or total <= 0:
                return None
            await self.cache.set_grams(cache_unit, food_name, value)
            return total
        except Exception as error:
            logger.warning("LLM recovered weight estimation failed: %s", error)
            return None

    async def estimate_nutrients(self, food_name: str) -> NutrientSet | None:
        if not self.settings.enabled or not self.settings.api_key:
            return None
        cached = await self.cache.get_llm_nutrients(food_name)
        if cached is not None:
            return cached
        try:
            await self.limiter.wait("llm")
            content = await self.runner.complete(
                build_nutrients_prompt(food_name),
                max_tokens=int(self.settings.max_tokens_nutrients),
            )
            if not content or not content.strip():
                return None
            raw = json.loads(re.sub(r"\x60\x60\x60json\n?|\n?\x60\x60\x60", "", content.strip()))
            values: dict[str, float | None] = {}
            for field, key in KEYS.items():
                value = js_number(raw.get(key))
                values[field] = None if math.isnan(value) or value == 0 else value
            fat = values["fat_per100g"]
            values["unsaturated_fat_per100g"] = (
                js_round(
                    (
                        fat
                        - (values["saturated_fat_per100g"] or 0)
                        - (values["trans_fat_per100g"] or 0)
                    )
                    * 10
                )
                / 10
                if fat is not None
                else None
            )
            nutrients = NutrientSet(**values)
            if nutrients.kcal_per100g is not None and nutrients.kcal_per100g > 0:
                await self.cache.set_llm_nutrients(food_name, nutrients)
                return nutrients
        except Exception as error:
            logger.warning("LLM nutrient estimation failed: %s", error)
        return None
