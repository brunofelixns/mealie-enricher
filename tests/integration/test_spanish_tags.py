import asyncio
import copy
import json

import httpx
import pytest
import respx

from mealie_enricher.app import create_app
from mealie_enricher.config import load_settings
from tests.parity.cases import load_case


@pytest.mark.parametrize("trigger", ["webhook", "backfill"])
async def test_legacy_tags_are_replaced_without_reestimating_or_removing_user_tags(
    trigger, tmp_path
):
    case = load_case("route-webhook-unchanged")
    recipe = copy.deepcopy(case["input"]["recipe"])
    recipe["tags"].extend(
        [
            {"id": "personal", "name": "Mi etiqueta", "slug": "mi-etiqueta", "groupId": None},
            {
                "id": "user-english",
                "name": "Digest:Easy",
                "slug": "personal-digest",
                "groupId": None,
            },
        ]
    )
    original_hash = recipe["extras"]["calorie_estimator_hash"]
    settings = load_settings(
        {
            **case["environment"],
            "CACHE_DB_PATH": str(tmp_path / "cache.db"),
        }
    )
    created, patches = [], []
    names_to_slugs = {
        "Calorías:Moderadas": "calorias-moderadas",
        "Digestión:Fácil": "digestion-facil",
    }

    def respond(request):
        assert request.url.host == "127.0.0.1", "Tag translation must not call OFF or an LLM"
        if request.url.path == "/api/recipes":
            return httpx.Response(200, json={"items": [{"slug": recipe["slug"]}], "total_pages": 1})
        if request.url.path == "/api/organizers/tags":
            name = json.loads(request.content)["name"]
            created.append(name)
            return httpx.Response(
                200,
                json={
                    "id": name,
                    "name": name,
                    "slug": names_to_slugs[name],
                    "groupId": None,
                },
            )
        if request.method == "PATCH":
            patch = json.loads(request.content)
            patches.append(patch)
            recipe.update(patch)
        return httpx.Response(200, json=recipe)

    with respx.mock as router:
        router.route().mock(side_effect=respond)
        async with httpx.AsyncClient() as external:
            app = create_app(settings, http=external)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://app.test",
                ) as client:
                    payload = (
                        {
                            "document_data": {
                                "document_type": "recipe",
                                "recipe_slug": recipe["slug"],
                            }
                        }
                        if trigger == "webhook"
                        else {}
                    )
                    assert (await client.post("/" + trigger, json=payload)).status_code == 202
                    while app.state.tasks.pending:
                        await asyncio.gather(*list(app.state.tasks.pending))
                    assert [r.status for r in app.state.history.get_history()] == ["tags-added"]
                    assert created == ["Calorías:Moderadas", "Digestión:Fácil"]
                    assert len(patches) == 1
                    assert "nutrition" not in patches[0]
                    assert patches[0]["extras"]["calorie_estimator_hash"] == original_hash
                    assert patches[0]["extras"]["foreign"] == "preserve"
                    assert {tag["slug"] for tag in patches[0]["tags"]} == {
                        "mi-etiqueta",
                        "personal-digest",
                        "calorias-moderadas",
                        "digestion-facil",
                    }
                    assert json.loads(patches[0]["extras"]["calorie_estimator_tags"]) == [
                        "calorias-moderadas",
                        "digestion-facil",
                    ]
                    await client.post(
                        "/webhook",
                        json={
                            "document_data": {
                                "document_type": "recipe",
                                "recipe_slug": recipe["slug"],
                            }
                        },
                    )
                    while app.state.tasks.pending:
                        await asyncio.gather(*list(app.state.tasks.pending))
                    assert len(patches) == 1
                    assert sorted(r.status for r in app.state.history.get_history()) == [
                        "skipped",
                        "tags-added",
                    ]
