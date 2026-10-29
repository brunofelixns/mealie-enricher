import asyncio
import copy
import json

import httpx
import respx

from mealie_enricher.app import create_app
from mealie_enricher.config import load_settings
from tests.parity.cases import load_case


async def test_webhook_and_backfill_share_serialization_and_do_not_duplicate_patch(tmp_path):
    case = load_case("route-webhook-normal")
    recipe = copy.deepcopy(case["input"]["recipe"])
    settings = load_settings(
        {
            **case["environment"],
            "CACHE_DB_PATH": str(tmp_path / "cache.db"),
            "EVENT_DEBOUNCE_MS": "1",
        }
    )
    patches = []

    def respond(request):
        path = request.url.path
        if request.url.host == "search.openfoodfacts.org":
            return httpx.Response(
                200,
                json={"hits": [{"product_name": "rice", "nutriments": {"energy-kcal_100g": 101}}]},
            )
        if path == "/api/recipes":
            return httpx.Response(200, json={"items": [{"slug": recipe["slug"]}], "total_pages": 1})
        if path == "/api/organizers/tags":
            name = json.loads(request.content)["name"]
            return httpx.Response(
                200,
                json={
                    "id": name,
                    "name": name,
                    "slug": name.lower().replace(":", "-"),
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
                    transport=httpx.ASGITransport(app=app), base_url="http://app.test"
                ) as client:
                    await asyncio.gather(
                        client.post(
                            "/webhook",
                            json={
                                "document_data": {
                                    "document_type": "recipe",
                                    "recipe_slug": recipe["slug"],
                                }
                            },
                        ),
                        client.post("/backfill", json={}),
                    )
                    while app.state.tasks.pending:
                        await asyncio.gather(*list(app.state.tasks.pending))
                    statuses = [record.status for record in app.state.history.get_history()]
    assert len(patches) == 1
    assert sorted(statuses) == ["processed", "skipped"]
