import asyncio
import json

import httpx
import pytest
import respx

from mealie_enricher.clients.mealie import MealieClient
from mealie_enricher.config import load_settings
from mealie_enricher.models import MealieRecipePatch
from tests.parity.cases import load_case


async def test_pagination_subpath_tokens_and_204_patch():
    settings = load_settings(
        {"MEALIE_URL": "https://mealie.test/prefix", "MEALIE_API_TOKEN_house": "synthetic"}
    )
    with respx.mock as router:
        router.get(
            "https://mealie.test/api/recipes?page=1&per_page=100&order_direction=asc"
        ).respond(200, json={"items": [{"slug": "one"}], "total_pages": 2})
        router.get(
            "https://mealie.test/api/recipes?page=2&per_page=100&order_direction=asc"
        ).respond(200, json={"items": [{"slug": "two"}], "total_pages": 2})
        patch = router.patch("https://mealie.test/api/recipes/one").respond(204)
        async with httpx.AsyncClient() as http:
            client = MealieClient(settings, http)
            assert await client.get_all_recipes("house") == ["one", "two"]
            assert (
                await client.patch_recipe(
                    "one", MealieRecipePatch(extras={"key": "value"}), "house"
                )
                is None
            )
        assert patch.calls[0].request.headers["authorization"] == "Bearer synthetic"


async def test_patch_failure_is_not_retried_and_retains_original_message():
    settings = load_settings({"MEALIE_URL": "https://mealie.test", "MEALIE_API_TOKEN": "test"})
    with respx.mock as router:
        route = router.patch("https://mealie.test/api/recipes/rice").respond(503, text="failure")
        async with httpx.AsyncClient() as http:
            with pytest.raises(ValueError, match="Mealie API 503 Service Unavailable"):
                await MealieClient(settings, http).patch_recipe(
                    "rice", MealieRecipePatch(extras={})
                )
        assert route.call_count == 1


async def test_mealie_timeout_and_invalid_json_keep_readable_errors():
    settings = load_settings({"MEALIE_URL": "https://mealie.test", "MEALIE_API_TOKEN": "test"})
    with respx.mock as router:
        router.get("https://mealie.test/api/recipes/timeout").mock(
            side_effect=httpx.ReadTimeout("timeout")
        )
        router.get("https://mealie.test/api/recipes/bad-json").respond(200, text="bad json")
        async with httpx.AsyncClient() as http:
            client = MealieClient(settings, http)
            with pytest.raises(ValueError, match="Mealie API request timed out: GET"):
                await client.get_recipe("timeout")
            with pytest.raises(ValueError, match="Invalid JSON from Mealie API"):
                await client.get_recipe("bad-json")


async def test_duplicate_tag_creation_falls_back_to_existing_tag():
    settings = load_settings({"MEALIE_URL": "https://mealie.test", "MEALIE_API_TOKEN": "test"})
    tag = {"id": "one", "name": "Calories:Light", "slug": "calories-light", "groupId": None}
    with respx.mock as router:
        router.post("https://mealie.test/api/organizers/tags").respond(409)
        router.get("https://mealie.test/api/organizers/tags?perPage=-1").respond(
            200, json={"items": [tag]}
        )
        async with httpx.AsyncClient() as http:
            tags = await MealieClient(settings, http).get_or_create_tags(["Calories:Light"])
        assert [item.model_dump(by_alias=True) for item in tags] == [tag]


async def test_slow_response_has_overall_deadline_and_no_retries():
    settings = load_settings(
        {
            "MEALIE_URL": "https://mealie.test",
            "MEALIE_API_TOKEN": "test",
            "MEALIE_TIMEOUT_MS": "25",
        }
    )
    calls = []

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            for chunk in [b'{"slug":', b'"slow"', b"}"]:
                await asyncio.sleep(0.015)
                yield chunk

    async def respond(request):
        calls.append(request)
        return httpx.Response(200, stream=SlowBody())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ValueError, match="Mealie API request timed out: GET"):
            await MealieClient(settings, http).get_recipe("slow")
    assert len(calls) == 1


async def test_json_extras_and_food_alias_objects_do_not_prevent_reading_recipe():
    recipe = load_case("route-estimate-normal")["input"]["recipe"]
    recipe["extras"]["nested"] = {"count": 2, "enabled": True}
    recipe["extras"]["numeric"] = 42
    recipe["recipeIngredient"][0]["food"]["aliases"] = [{"name": "Flour", "id": "alias"}]
    settings = load_settings({"MEALIE_URL": "https://mealie.test", "MEALIE_API_TOKEN": "test"})
    with respx.mock as router:
        router.get("https://mealie.test/api/recipes/" + recipe["slug"]).respond(200, json=recipe)
        patch = router.patch("https://mealie.test/api/recipes/" + recipe["slug"]).respond(204)
        async with httpx.AsyncClient() as http:
            client = MealieClient(settings, http)
            result = await client.get_recipe(recipe["slug"])
            await client.patch_recipe(recipe["slug"], MealieRecipePatch(extras=result.extras))
        assert json.loads(patch.calls.last.request.content)["extras"] == recipe["extras"]
