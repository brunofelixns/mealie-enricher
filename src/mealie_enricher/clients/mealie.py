import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..config import Settings, get_mealie_token
from ..models import MealieRecipe, MealieRecipePatch, MealieTag


def get_recipe_household_id(recipe: MealieRecipe) -> str | None:
    return recipe.household_id if recipe.household_id is not None else recipe.legacy_household_id


class MealieClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings, self.http = settings, http
        base = urlsplit(settings.mealie.url)
        self.origin = base.scheme + "://" + base.netloc

    async def _request(
        self, method: str, path: str, body: Any = None, household_id: str | None = None
    ) -> Any:
        url = self.origin + path
        try:
            async with asyncio.timeout(self.settings.mealie.timeout_ms / 1000):
                response = await self.http.request(
                    method,
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + get_mealie_token(self.settings, household_id),
                    },
                    **({"json": body} if body is not None else {}),
                    timeout=self.settings.mealie.timeout_ms / 1000,
                    follow_redirects=False,
                )
        except (httpx.TimeoutException, TimeoutError) as error:
            raise ValueError(f"Mealie API request timed out: {method} {url}") from error
        if not response.is_success:
            raise ValueError(
                f"Mealie API {response.status_code} {response.reason_phrase}: "
                f"{url} — {response.text[:200]}"
            )
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError as error:
            raise ValueError("Invalid JSON from Mealie API") from error

    async def get_recipe(self, slug: str, household_id: str | None = None) -> MealieRecipe:
        data = await self._request("GET", "/api/recipes/" + slug, household_id=household_id)
        return MealieRecipe.model_validate(data)

    async def patch_recipe(
        self, slug: str, patch: MealieRecipePatch, household_id: str | None = None
    ) -> None:
        await self._request(
            "PATCH",
            "/api/recipes/" + slug,
            patch.model_dump(by_alias=True, exclude_unset=True),
            household_id,
        )

    async def get_all_recipes(self, household_id: str | None = None) -> list[str]:
        slugs: list[str] = []
        page = 1
        while True:
            data = await self._request(
                "GET",
                f"/api/recipes?page={page}&per_page=100&order_direction=asc",
                household_id=household_id,
            )
            slugs.extend(item["slug"] for item in data["items"])
            if page >= data["total_pages"]:
                return slugs
            page += 1

    async def get_or_create_tags(
        self, names: list[str], household_id: str | None = None
    ) -> list[MealieTag]:
        async def create(name: str) -> MealieTag | None:
            try:
                data = await self._request(
                    "POST", "/api/organizers/tags", {"name": name}, household_id
                )
                return MealieTag.model_validate(data)
            except Exception:
                return None

        created = await asyncio.gather(*(create(name) for name in names))
        if all(item is not None for item in created):
            return [item for item in created if item is not None]
        existing = await self._request(
            "GET", "/api/organizers/tags?perPage=-1", household_id=household_id
        )
        by_name = {item["name"]: MealieTag.model_validate(item) for item in existing["items"]}
        resolved = [
            item if item is not None else by_name.get(name)
            for name, item in zip(names, created, strict=True)
        ]
        return [item for item in resolved if item is not None]
