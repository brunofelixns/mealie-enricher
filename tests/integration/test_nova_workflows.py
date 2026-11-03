import asyncio
import copy
import json

import httpx
import httpx2
import pytest
from openai import AsyncOpenAI

from mealie_enricher.app import create_app
from mealie_enricher.config import load_settings
from mealie_enricher.models import MealieRecipe
from tests.integration.test_nova_decisions import response


def sample_recipe():
    return {
        "slug": "arroz",
        "name": "Arroz con tomate",
        "recipeServings": 1,
        "recipeIngredient": [
            {"quantity": 100, "unit": {"name": "g"}, "food": {"name": "Arroz"}},
        ],
        "recipeInstructions": [{"text": "Cocer"}],
        "extras": {"personal": "conservar"},
        "tags": [{"id": "personal", "name": "Mi receta", "slug": "mi-receta"}],
    }


def install_provider(monkeypatch, handler):
    from mealie_enricher.agents import nova_decisions

    monkeypatch.setattr(
        nova_decisions,
        "AsyncOpenAI",
        lambda **kwargs: AsyncOpenAI(
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)), **kwargs
        ),
    )


def configure(tmp_path):
    return load_settings(
        {
            "MEALIE_API_TOKEN": "test-mealie",
            "MEALIE_URL": "http://mealie.test",
            "CACHE_DB_PATH": str(tmp_path / "cache.db"),
            "NOVA_ENABLED": "true",
            "OPENAI_API_KEY": "test-nova",
            "EVENT_DEBOUNCE_MS": "1",
        }
    )


def mealie_transport(recipe, patches, *, allow_off=False):
    def respond(request):
        if request.url.host == "search.openfoodfacts.org" and allow_off:
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "product_name": "Arroz",
                            "nutriments": {"energy-kcal_100g": 100},
                        }
                    ]
                },
            )
        assert request.url.host == "mealie.test", "NOVA-only updates must not estimate nutrition"
        if request.url.path == "/api/recipes":
            return httpx.Response(200, json={"items": [{"slug": "arroz"}], "total_pages": 1})
        if request.url.path == "/api/organizers/tags":
            name = json.loads(request.content)["name"]
            return httpx.Response(
                200,
                json={
                    "id": name,
                    "name": name,
                    "slug": name.lower().replace(":", "-"),
                },
            )
        if request.method == "PATCH":
            patch = json.loads(request.content)
            patches.append(copy.deepcopy(patch))
            recipe.update(patch)
        return httpx.Response(200, json=recipe)

    return httpx.MockTransport(respond)


@pytest.mark.parametrize("trigger", ["webhook", "backfill"])
async def test_existing_complete_recipe_gets_nova_without_nutrition_changes_or_webhook_loop(
    monkeypatch, tmp_path, trigger
):
    calls = []

    def provider(request):
        calls.append(request)
        return httpx2.Response(200, json=response())

    install_provider(monkeypatch, provider)
    recipe, patches = sample_recipe(), []
    recipe["tags"].append({"id": "digest", "name": "Digestión:Fácil", "slug": "digestion-facil"})
    recipe["extras"]["calorie_estimator_tags"] = '["digestion-facil"]'
    recipe["nutrition"] = {"calories": "123"}  # Partial nutrition must also be preserved.
    ingredients = copy.deepcopy(recipe["recipeIngredient"])
    async with httpx.AsyncClient(transport=mealie_transport(recipe, patches)) as external:
        app = create_app(configure(tmp_path), http=external)
        async with app.router.lifespan_context(app):
            recipe["extras"]["calorie_estimator_hash"] = (
                app.state.processing.tagging.estimator.ingredient_hash(
                    MealieRecipe.model_validate(recipe)
                )
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://app.test"
            ) as client:
                payload = {"document_data": {"document_type": "recipe", "recipe_slug": "arroz"}}
                assert (await client.post("/" + trigger, json=payload)).status_code == 202
                while app.state.tasks.pending:
                    await asyncio.gather(*list(app.state.tasks.pending))
            assert len(patches) == 1
            assert "nutrition" not in patches[0]
            assert recipe["extras"]["personal"] == "conservar"
            assert {tag["name"] for tag in recipe["tags"]} == {
                "Mi receta",
                "Digestión:Fácil",
                "NOVA:1",
            }
            assert recipe["recipeIngredient"] == ingredients
            trace = json.loads(recipe["extras"]["calorie_estimator_nova"])
            assert trace["group"] == 1
            assert trace["confidence"] == 0.98
            assert trace["model"] == "gpt-6-luna"
            await app.state.processing.process_webhook("arroz")
            assert len(patches) == 1
            assert len(calls) == 1
            # Removing only the applied tag repairs it from the cached assessment.
            recipe["tags"] = [tag for tag in recipe["tags"] if tag["name"] != "NOVA:1"]
            await app.state.processing.process_webhook("arroz")
            assert len(patches) == 2
            assert len(calls) == 1
            assert "nutrition" not in patches[-1]
            # Instructions do not affect the legacy nutrition hash, but do affect NOVA.
            recipe["recipeInstructions"] = [{"text": "Servir con queso curado"}]
            await app.state.processing.process_webhook("arroz")
            assert len(calls) == 2
            assert len(patches) == 3
            assert "nutrition" not in patches[-1]


async def test_nova_is_applied_while_manual_calories_are_acknowledged(monkeypatch, tmp_path):
    install_provider(
        monkeypatch, lambda request: httpx2.Response(200, json=response(choice="nova_3"))
    )
    recipe, patches = sample_recipe(), []
    recipe["nutrition"] = {"calories": "500", "proteinContent": "10"}
    recipe["extras"]["calorie_estimator_nova"] = "{}"  # Stale metadata must be replaced.
    original_nutrition = copy.deepcopy(recipe["nutrition"])
    async with httpx.AsyncClient(transport=mealie_transport(recipe, patches)) as external:
        app = create_app(configure(tmp_path), http=external)
        async with app.router.lifespan_context(app):
            await app.state.processing.process_webhook("arroz")
            assert len(patches) == 1
            assert "nutrition" not in patches[0]
            assert recipe["nutrition"] == original_nutrition
            assert {tag["name"] for tag in recipe["tags"]} == {"Mi receta", "NOVA:3"}
            assert app.state.history.get_history()[0].status == "manual"
            await app.state.processing.process_webhook("arroz")
            assert len(patches) == 1


@pytest.mark.parametrize("provider_status", [200, 500])
async def test_forced_estimation_adds_nova_and_survives_provider_failure(
    monkeypatch, tmp_path, provider_status
):
    calls = []

    def provider(request):
        calls.append(request)
        return httpx2.Response(provider_status, json=response(choice="nova_4"))

    install_provider(monkeypatch, provider)
    recipe, patches = sample_recipe(), []
    async with httpx.AsyncClient(
        transport=mealie_transport(recipe, patches, allow_off=True)
    ) as external:
        app = create_app(configure(tmp_path), http=external)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://app.test"
            ) as client:
                assert (
                    await client.post("/estimate", json={"content": {"slug": "arroz"}})
                ).status_code == 202
                while app.state.tasks.pending:
                    await asyncio.gather(*list(app.state.tasks.pending))
            assert len(patches) == 1
            assert patches[0]["nutrition"]["calories"] == "100"
            expected = "NOVA:4" if provider_status == 200 else "NOVA:Desconocida"
            assert expected in {tag["name"] for tag in recipe["tags"]}
            assert app.state.history.get_history()[0].status == "processed"
            await app.state.processing.process_webhook("arroz")
            assert len(calls) == 1
            assert len(patches) == 1
            await app.state.processing.process_estimate("arroz")
            assert len(calls) == 2
            assert len(patches) == 2


@pytest.mark.parametrize("fail_all_tags", [False, True])
async def test_unavailable_mealie_nova_tag_never_claims_a_nutrition_slug_or_repeats_patches(
    monkeypatch, tmp_path, fail_all_tags
):
    calls = []

    def provider(request):
        calls.append(request)
        return httpx2.Response(200, json=response())

    install_provider(monkeypatch, provider)
    recipe, patches = sample_recipe(), []
    base = mealie_transport(recipe, patches, allow_off=True)

    async def respond(request):
        if request.url.path == "/api/organizers/tags":
            if request.method == "GET":
                return httpx.Response(200, json={"items": []})
            name = json.loads(request.content)["name"]
            if name.startswith("NOVA:") or fail_all_tags:
                return httpx.Response(500, text="Tag temporarily unavailable")
        return await base.handle_async_request(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as external:
        app = create_app(configure(tmp_path), http=external)
        async with app.router.lifespan_context(app):
            await app.state.processing.process_estimate("arroz")
            assert len(patches) == 1
            assert patches[0]["nutrition"]["calories"] == "100"
            assessment = json.loads(recipe["extras"]["calorie_estimator_nova"])
            assert assessment["group"] == 1
            assert assessment["tag_slug"] is None
            assert assessment["tag_status"] == "unavailable"
            assert "Mi receta" in {tag["name"] for tag in recipe["tags"]}
            await app.state.processing.process_webhook("arroz")
            assert len(patches) == 1
            assert len(calls) == 1
