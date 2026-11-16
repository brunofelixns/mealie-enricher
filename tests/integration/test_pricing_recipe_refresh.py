import asyncio
import copy
import json
import time
from contextlib import asynccontextmanager

import httpx
import pytest

from mealie_enricher.app import create_app
from mealie_enricher.pricing.service import PricingDeferred, PricingService
from mealie_enricher.runtime.slug_queue import SlugQueue
from tests.integration.test_pricing_service import Mealie, Selector, settings, snapshot

HEADERS = {"Authorization": "Bearer pricing-admin-test-token", "Origin": "http://test"}


@asynccontextmanager
async def pricing_app(tmp_path):
    config = settings(tmp_path / "pricing")
    config.cache.db_path = str(tmp_path / "cache.db")
    app = create_app(config)
    async with app.router.lifespan_context(app):
        service = app.state.pricing
        await service.selector.close()
        service.selector = Selector()
        service.mealie = Mealie()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield service, client


async def test_missing_catalog_defers_pricing_without_wiping_recipe_data(tmp_path):
    mealie = Mealie()
    mealie.recipe.extras["mealie_enricher_pricing"] = '{"previous": "keep"}'
    before = copy.deepcopy(mealie.recipe.model_dump())
    async with httpx.AsyncClient() as http:
        service = PricingService(settings(tmp_path), http, mealie, SlugQueue(), selector=Selector())
        try:
            with pytest.raises(PricingDeferred, match="catalog"):
                await service.process_slug(mealie.recipe.slug)
            assert mealie.recipe.model_dump() == before
            assert mealie.patches == []
            assert service.state.data["pending_refresh"]
        finally:
            await service.close()


async def test_forced_recipe_endpoint_checks_auth_and_requires_a_catalog(tmp_path):
    async with pricing_app(tmp_path) as (service, client):
        response = await client.post("/pricing/recipes/refresh")
        assert response.status_code == 401
        response = await client.post("/pricing/recipes/refresh", headers=HEADERS)
        assert response.status_code == 409
        assert "catalog" in response.text.lower()
        assert service.mealie.patches == []


async def test_forced_recipe_endpoint_revisits_cache_and_exposes_live_recipe_progress(tmp_path):
    async with pricing_app(tmp_path) as (service, client):
        service.store.publish(snapshot(competitor=True))
        await service.refresh()
        previous_calls = service.selector.calls
        entered, release = asyncio.Event(), asyncio.Event()
        original = service.process_slug

        async def paused(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)

        service.process_slug = paused
        try:
            response = await client.post("/pricing/recipes/refresh", headers=HEADERS)
            assert response.status_code == 202
            assert response.json()["status"] == "accepted"
            await asyncio.wait_for(entered.wait(), 2)
            response = await client.get("/pricing/progress", headers=HEADERS)
            live = response.json()["recipes"]
            assert live["running"]
            assert live["completed"] == 0
            assert live["total"] == 1
            assert live["current"] == "arroz-pollo"
            duplicate = await client.post("/pricing/recipes/refresh", headers=HEADERS)
            assert duplicate.json()["status"] == "running"
            release.set()
            await service._job
            assert service.selector.calls > previous_calls
            final = service.progress_status()["recipes"]
            assert not final["running"]
            assert final["completed"] == final["succeeded"] == final["total"] == 1
            assert final["failed"] == 0
            assert final["finished_at"] is not None
            result = json.loads(service.mealie.recipe.extras["mealie_enricher_pricing"])
            assert result["retailers"]["mercadona"]["total_cost"] is not None
        finally:
            release.set()


async def test_recipe_progress_counts_failures_without_claiming_all_recipes_updated(tmp_path):
    async with pricing_app(tmp_path) as (service, _client):
        service.store.publish(snapshot())
        original = service.mealie.get_recipe

        async def all_recipes(household_id=None):
            return ["arroz-pollo", "broken"]

        async def get_recipe(slug, household_id=None):
            if slug == "broken":
                raise ValueError("Recipe unavailable")
            return await original(slug, household_id)

        service.mealie.get_all_recipes = all_recipes
        service.mealie.get_recipe = get_recipe
        await service.refresh()
        result = service.progress_status()
        assert result["phase"] == "partial"
        assert result["recipes"]["completed"] == result["recipes"]["total"] == 2
        assert result["recipes"]["succeeded"] == 1
        assert result["recipes"]["failed"] == 1
        assert not result["recipes"]["running"]


async def test_failed_initial_sync_retries_download_instead_of_reviewing_empty_catalog(
    tmp_path, monkeypatch
):
    from mealie_enricher.pricing import service as module

    config = settings(tmp_path)
    config.pricing.auto_sync = True
    async with httpx.AsyncClient() as http:
        service = PricingService(config, http, Mealie(), SlugQueue(), selector=Selector())
        downloads = []

        async def failed(postal_code):
            raise ValueError("Mercadona HTTP 503")

        async def succeeded(postal_code):
            downloads.append(postal_code)
            return snapshot()

        async def stop_after_tick(_seconds):
            raise asyncio.CancelledError

        try:
            service.source.download = failed
            await service.sync(manual=False)
            assert service.status().get("pending_sync") is True
            assert time.time() < service.state.data["refresh_retry_at"] <= time.time() + 300
            service.state.data["refresh_retry_at"] = 0
            service.source.download = succeeded
            monkeypatch.setattr(module.asyncio, "sleep", stop_after_tick)
            service.start()
            with pytest.raises(asyncio.CancelledError):
                await service._scheduler
            if service._job is not None:
                await service._job
            assert downloads == ["27004"]
            assert not service.status()["pending_sync"]
            assert service.state.data["phase"] == "idle"
            assert service.mealie.patches
        finally:
            await service.close()


async def test_reviewed_recipe_with_unknown_quantity_is_not_counted_as_fully_priced(tmp_path):
    async with pricing_app(tmp_path) as (service, _client):
        service.store.publish(snapshot())
        service.mealie.recipe.recipe_ingredient[1].unit = None
        await service.refresh()
        recipes = service.progress_status()["recipes"]
        assert recipes["succeeded"] == 1
        assert recipes.get("priced") == 0
        assert recipes.get("incomplete") == 1


@pytest.mark.parametrize("source", ["original_text", "display"])
async def test_freeform_ingredient_search_excludes_quantity_without_inventing_costs(
    tmp_path, source
):
    async with pricing_app(tmp_path) as (service, _client):
        from mealie_enricher.models import MealieIngredient

        service.store.publish(snapshot())
        service.mealie.recipe.recipe_ingredient = [
            MealieIngredient(**{source: "Media taza de arroz"})
        ]
        before = copy.deepcopy(service.mealie.recipe.recipe_ingredient[0].model_dump())
        result = await service.process_slug("arroz-pollo")
        assert result["lines"][0]["product_id"] == "rice"
        assert result["lines"][0]["reason"] == "missing_quantity"
        assert result["total_cost"] is None
        assert service.mealie.recipe.recipe_ingredient[0].model_dump() == before


async def test_forced_review_retries_reselect_remaining_cached_products_with_a_bounded_budget(
    tmp_path,
):
    from mealie_enricher.pricing.models import Product

    async with pricing_app(tmp_path) as (service, _client):
        catalog = snapshot(competitor=True)
        catalog.products.append(
            Product(
                id="chicken2",
                name="Pollo alternativo",
                package_quantity=1000,
                package_unit="g",
                price="2.00",
            )
        )
        service.store.publish(catalog)
        service.mealie.recipe.model_extra["description"] = "A recipe with context"
        selector = service.selector
        original_choose = selector.choose

        async def expensive(_recipe, _ingredient, candidates, **kwargs):
            return next(p.id for p in candidates if p.id in {"rice", "chicken"}), 0.99

        selector.choose = expensive
        await service.refresh()
        selector.choose = original_choose
        service.config.max_decisions_per_run = 1
        await service.refresh(force=True)
        assert service.status()["pending_refresh"]
        await service.refresh()
        result = json.loads(service.mealie.recipe.extras["mealie_enricher_pricing"])
        assert [line["product_id"] for line in result["retailers"]["mercadona"]["lines"]] == [
            "rice2",
            "chicken2",
        ]
        assert selector.calls == 2
        assert not service.status()["pending_refresh"]


def test_recipe_review_is_not_still_running_after_an_interrupted_restart(tmp_path):
    from mealie_enricher.pricing.progress import PricingProgress
    from mealie_enricher.pricing.state import PricingState

    state = PricingState(str(tmp_path))
    state.data.update(running=True, phase="refreshing")
    tracker = PricingProgress(state)
    tracker.begin("refreshing")
    tracker.update_recipes(1, 0, 3, "arroz-pollo")
    restarted = PricingState(str(tmp_path))
    result = PricingProgress(restarted).snapshot()
    assert not result["recipes"]["running"]
    assert result["recipes"]["completed"] == 1
    assert result["recipes"]["finished_at"] is not None


@pytest.mark.parametrize("endpoint", ["/webhook", "/estimate", "/backfill"])
async def test_all_recipe_entrypoints_apply_mercadona_even_when_nutrition_is_filtered(
    tmp_path, endpoint
):
    from tests.integration.test_pricing_service import recipe

    config = settings(tmp_path / "pricing")
    config.cache.db_path = str(tmp_path / "cache.db")
    config.estimate.strategy = "tag"
    config.events.debounce_ms = 0
    wire = recipe().model_dump(by_alias=True)
    original_ingredients = copy.deepcopy(wire["recipeIngredient"])

    def handler(request):
        if request.url.path == "/api/recipes":
            return httpx.Response(200, json={"items": [{"slug": wire["slug"]}], "total_pages": 1})
        if request.url.path == "/api/organizers/tags" and request.method == "POST":
            name = json.loads(request.content)["name"]
            return httpx.Response(200, json={"id": name, "name": name, "slug": name})
        if request.method == "PATCH":
            patch = json.loads(request.content)
            assert "nutrition" not in patch
            wire.update(patch)
        return httpx.Response(200, json=wire)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as external:
        app = create_app(config, http=external)
        async with app.router.lifespan_context(app):
            service = app.state.pricing
            await service.selector.close()
            service.selector = Selector()
            service.store.publish(snapshot())
            body = {
                "/webhook": {
                    "document_data": {"recipe_slug": wire["slug"], "document_type": "recipe"}
                },
                "/estimate": {"content": {"slug": wire["slug"]}},
                "/backfill": {},
            }[endpoint]
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(endpoint, json=body)
                assert response.status_code == 202
                await asyncio.gather(*list(app.state.tasks.pending))
            assert app.state.history.get_history()[0].status == "filtered"
            result = json.loads(wire["extras"]["mealie_enricher_pricing"])["retailers"]["mercadona"]
            assert result["complete"]
            assert result["total_cost"] == "6.00"
            assert result["per_serving_cost"] == "1.50"
            assert wire["nutrition"]["calories"] == "manual-300"
            assert wire["recipeIngredient"] == original_ingredients
