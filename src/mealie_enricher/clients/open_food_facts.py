import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from urllib.parse import urlencode

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..compat import js_round
from ..config import OffSettings
from ..models import NutrientSet, OffLookupResult
from ..runtime.rate_limiter import RateLimiter
from ..storage.cache import SqliteCache

logger = logging.getLogger(__name__)
NUTRIENTS = {
    "kcal_per100g": "energy-kcal_100g",
    "protein_per100g": "proteins_100g",
    "carbs_per100g": "carbohydrates_100g",
    "fat_per100g": "fat_100g",
    "saturated_fat_per100g": "saturated-fat_100g",
    "trans_fat_per100g": "trans-fat_100g",
    "fiber_per100g": "fiber_100g",
    "sugar_per100g": "sugars_100g",
    "sodium_per100g": "sodium_100g",
    "cholesterol_per100g": "cholesterol_100g",
}


class _TransientOffError(Exception):
    pass


class OffClient:
    def __init__(
        self,
        settings: OffSettings,
        http: httpx.AsyncClient,
        cache: SqliteCache,
        limiter: RateLimiter,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.settings, self.http, self.cache, self.limiter = settings, http, cache, limiter
        self.sleep = sleep

    async def lookup_nutrients(
        self, food_name: str, unit_name: str | None = None
    ) -> OffLookupResult:
        cached = await self.cache.get_nutrients(food_name)
        if cached is not None:
            return OffLookupResult(nutrients=cached, matched=True, product_name=food_name)
        term = food_name
        if unit_name and term.lower().startswith(unit_name.lower()):
            term = term[len(unit_name) :].strip()
        query = urlencode(
            {
                "q": term,
                "langs": self.settings.language,
                "page_size": "1",
                "fields": "product_name,nutriments",
            }
        ).replace("~", "%7E")
        url = self.settings.search_base_url + "/search?" + query
        await self.limiter.wait("search")
        miss = OffLookupResult(nutrients=None, matched=False, product_name=None)
        if not math.isfinite(self.settings.max_retries) or self.settings.max_retries < 0:
            return miss
        response: httpx.Response | None = None
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(int(self.settings.max_retries) + 1),
                wait=wait_exponential(multiplier=self.settings.retry_backoff_ms / 1000, min=0),
                retry=retry_if_exception_type((_TransientOffError, httpx.HTTPError)),
                sleep=self.sleep,
                reraise=True,
            ):
                with attempt:
                    response = await self.http.get(
                        url,
                        headers={"User-Agent": self.settings.user_agent},
                        timeout=None,
                        follow_redirects=True,
                    )
                    if response.status_code in {429, 500, 502, 503, 504}:
                        raise _TransientOffError(str(response.status_code))
            if response is None or not response.is_success:
                return miss
            data = response.json()
            hits = data.get("hits")
            if not hits:
                return miss
            product = hits[0]
            raw = product.get("nutriments")
            name = product.get("product_name")
            if not raw or raw.get("energy-kcal_100g") is None:
                return OffLookupResult(nutrients=None, matched=False, product_name=name)
            values = {key: raw.get(alias) for key, alias in NUTRIENTS.items()}
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
            await self.cache.set_nutrients(food_name, nutrients)
            return OffLookupResult(nutrients=nutrients, matched=True, product_name=name)
        except Exception as error:
            logger.warning("OFF search failed: %s", error)
            return miss
