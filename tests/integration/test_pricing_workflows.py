import copy
import json

import httpx

from mealie_enricher.app import create_app
from mealie_enricher.models import MealieRecipe
from tests.integration.test_pricing_service import recipe, settings, snapshot


async def test_unchanged_nutrition_webhook_still_prices_and_preserves_foreign_fields(tmp_path):
    config = settings(tmp_path)
    config.cache.db_path = str(tmp_path / "cache.db")
    wire = recipe().model_dump(by_alias=True)
    patches = []

    def handler(request):
        if request.url.path == "/api/organizers/tags" and request.method == "POST":
            name = json.loads(request.content)["name"]
            return httpx.Response(200, json={"name": name, "id": name, "slug": name})
        if request.method == "PATCH":
            patch = json.loads(request.content)
            patches.append(copy.deepcopy(patch))
            wire.update(patch)
        return httpx.Response(200, json=wire)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as external:
        app = create_app(config, http=external)
        async with app.router.lifespan_context(app):
            app.state.pricing.store.publish(snapshot())
            wire["extras"]["calorie_estimator_hash"] = (
                app.state.processing.tagging.estimator.ingredient_hash(
                    MealieRecipe.model_validate(wire)
                )
            )
            app.state.processing.tagging.tags_are_complete = lambda recipe: True
            await app.state.processing.process_webhook(wire["slug"])
            assert app.state.history.get_history()[0].status == "skipped"
            assert len(patches) == 1
            assert "nutrition" not in patches[0]
            assert wire["nutrition"]["calories"] == "manual-300"
            assert wire["extras"]["personal"] == {"keep": True}
            assert "Mercadona:1,50 €/ración" in {tag["name"] for tag in wire["tags"]}
