import asyncio
import copy
import json
import threading
import time
import uuid
from decimal import Decimal

import httpx
import pytest

from mealie_enricher.config import load_settings
from mealie_enricher.models import MealieRecipe, MealieTag
from mealie_enricher.pricing.models import Product, Snapshot
from mealie_enricher.runtime.slug_queue import SlugQueue


def settings(tmp_path):
    return load_settings(
        {
            "MEALIE_API_TOKEN": "test",
            "OPENAI_API_KEY": "test-key",
            "PRICING_ENABLED": "true",
            "PRICING_AUTO_SYNC": "false",
            "PRICING_ADMIN_TOKEN": "pricing-admin-test-token",
            "PRICING_DATA_DIR": str(tmp_path),
        }
    )


def recipe():
    return MealieRecipe.model_validate(
        {
            "slug": "arroz-pollo",
            "name": "Arroz con pollo",
            "recipeServings": 4,
            "householdId": "home",
            "nutrition": {"calories": "manual-300"},
            "recipeIngredient": [
                {"quantity": 500, "unit": {"name": "g"}, "food": {"name": "Arroz"}},
                {"quantity": 600, "unit": {"name": "g"}, "food": {"name": "Pollo"}},
            ],
            "extras": {"personal": {"keep": True}, "calorie_estimator_hash": "unchanged"},
            "tags": [{"id": "personal", "name": "Favorita", "slug": "favorita"}],
        }
    )


def snapshot(price="4.80", competitor=False):
    products = [
        Product(id="rice", name="Arroz", package_quantity=1000, package_unit="g", price=price),
        Product(id="chicken", name="Pollo", package_quantity=1000, package_unit="g", price="6.00"),
    ]
    if competitor:
        products.append(
            Product(
                id="rice2",
                name="Arroz alternativo",
                package_quantity=1000,
                package_unit="g",
                price="1.00",
            )
        )
    return Snapshot(
        postal_code="27004", warehouse="4450", observed_at="2026-11-03T00:00:00Z", products=products
    )


class Mealie:
    def __init__(self):
        self.recipe = recipe()
        self.patches = []

    async def get_recipe(self, slug, household_id=None):
        return self.recipe.model_copy(deep=True)

    async def get_or_create_tags(self, names, household_id=None):
        return [MealieTag(id=name, name=name, slug=name) for name in names]

    async def patch_recipe(self, slug, patch, household_id=None):
        values = patch.model_dump(by_alias=True, exclude_unset=True)
        self.patches.append(copy.deepcopy(values))
        self.recipe = MealieRecipe.model_validate(
            {**self.recipe.model_dump(by_alias=True), **values}
        )

    async def get_all_recipes(self, household_id=None):
        return [self.recipe.slug]


class Selector:
    signature = "test-policy"

    def __init__(self):
        self.calls = 0

    async def choose(self, recipe, ingredient, candidates, **kwargs):
        self.calls += 1
        return min(candidates, key=lambda p: p.price or Decimal("100")).id, 0.99

    async def close(self):
        pass


async def test_exact_tags_extras_and_idempotence_preserve_manual_nutrition(tmp_path):
    from mealie_enricher.pricing.service import PRICING_EXTRA, PricingService

    mealie = Mealie()
    async with httpx.AsyncClient() as http:
        service = PricingService(settings(tmp_path), http, mealie, SlugQueue(), selector=Selector())
        try:
            service.store.publish(snapshot())
            await service.process_slug("arroz-pollo")
            result = json.loads(mealie.recipe.extras[PRICING_EXTRA])["retailers"]["mercadona"]
            assert result["per_serving_cost"] == "1.50"
            assert result["total_cost"] == "6.00"
            assert result["purchase_cost"] == "10.80"
            assert {tag.name for tag in mealie.recipe.tags} == {
                "Favorita",
                "Mercadona:1,50 €/ración",
                "Mercadona:10,80 € compra",
            }
            assert mealie.recipe.extras["personal"] == {"keep": True}
            assert mealie.recipe.nutrition.calories == "manual-300"
            assert "nutrition" not in mealie.patches[0]
            await service.process_slug("arroz-pollo")
            assert len(mealie.patches) == 1
        finally:
            await service.close()


async def test_new_competitor_invalidates_selection_and_replaces_only_owned_tags(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    mealie, selector = Mealie(), Selector()
    async with httpx.AsyncClient() as http:
        service = PricingService(settings(tmp_path), http, mealie, SlugQueue(), selector=selector)
        try:
            service.store.publish(snapshot())
            await service.process_slug("arroz-pollo")
            service.store.publish(snapshot(competitor=True))
            await service.process_slug("arroz-pollo")
            assert selector.calls == 1
            assert "Mercadona:1,50 €/ración" not in {t.name for t in mealie.recipe.tags}
            assert "Favorita" in {t.name for t in mealie.recipe.tags}
            await service.process_slug("arroz-pollo")
            assert selector.calls == 1
            assert len(mealie.patches) == 2
        finally:
            await service.close()


async def test_failed_sync_keeps_snapshot_and_manual_run_keeps_schedule(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    async with httpx.AsyncClient() as http:
        service = PricingService(
            settings(tmp_path), http, Mealie(), SlugQueue(), selector=Selector()
        )
        try:
            service.store.publish(snapshot())
            service.state.data["next_run"] = 9999999999

            async def failed(postal_code):
                raise RuntimeError("source unavailable")

            service.source.download = failed
            await service.sync(manual=True)
            assert service.state.data["next_run"] == 9999999999
            assert service.state.data["last_error"] == "RuntimeError"
            assert service.store.load("mercadona", "27004") is not None
            assert not service.state.data["running"]
        finally:
            await service.close()


async def test_manual_sync_coalesces_and_preserves_next_scheduled_run_after_restart(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    async with httpx.AsyncClient() as http:
        service = PricingService(
            settings(tmp_path), http, Mealie(), SlugQueue(), selector=Selector()
        )
        next_run = time.time() + 500
        service.state.data["next_run"] = next_run
        gate = asyncio.Event()
        calls = []

        async def download(postal_code):
            calls.append(postal_code)
            await gate.wait()
            return snapshot()

        service.source.download = download
        assert service.trigger("manual")
        assert not service.trigger("manual")
        gate.set()
        await service._job
        assert calls == ["27004"]
        assert service.state.data["next_run"] == next_run
        assert service.state.data["phase"] == "idle"
        await service.close()
        restarted = PricingService(
            settings(tmp_path), http, Mealie(), SlugQueue(), selector=Selector()
        )
        try:
            assert restarted.state.data["next_run"] == next_run
            assert restarted.store.load("mercadona", "27004") is not None
        finally:
            await restarted.close()


async def test_unique_nonidentical_name_still_requires_identity_verification(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    mealie, selector = Mealie(), Selector()
    async with httpx.AsyncClient() as http:
        service = PricingService(settings(tmp_path), http, mealie, SlugQueue(), selector=selector)
        try:
            data = snapshot()
            data.products[0] = data.products[0].model_copy(update={"name": "Caldo de arroz"})
            service.store.publish(data)
            await service.process_slug("arroz-pollo")
            assert selector.calls == 1
        finally:
            await service.close()


async def test_budget_exhaustion_leaves_recipe_review_pending_for_next_batch(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    async with httpx.AsyncClient() as http:
        service = PricingService(
            settings(tmp_path), http, Mealie(), SlugQueue(), selector=Selector()
        )
        try:
            data = snapshot(competitor=True)
            data.products[1] = data.products[1].model_copy(update={"name": "Pechuga de pollo"})
            service.store.publish(data)
            service.config.max_decisions_per_run = 1
            await service.refresh()
            assert service.state.data["pending_refresh"]
            assert service.state.data["phase"] == "partial"
            await service.refresh()
            assert not service.state.data["pending_refresh"]
            assert service.state.data["phase"] == "idle"
        finally:
            await service.close()


async def test_restart_reconciles_catalog_activated_before_state_was_saved(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    async with httpx.AsyncClient() as http:
        service = PricingService(
            settings(tmp_path), http, Mealie(), SlugQueue(), selector=Selector()
        )
        service.store.publish(snapshot())
        await service.refresh()
        assert not service.state.data["pending_refresh"]
        service.store.publish(snapshot(price="5.00"))
        await service.close()
        restarted = PricingService(
            settings(tmp_path), http, Mealie(), SlugQueue(), selector=Selector()
        )
        try:
            assert restarted.state.data["pending_refresh"]
        finally:
            await restarted.close()


async def test_shutdown_keeps_writer_ownership_until_publication_thread_finishes(tmp_path):
    from mealie_enricher.pricing.service import PricingService
    from mealie_enricher.pricing.state import PricingOwner

    async with httpx.AsyncClient() as http:
        service = PricingService(
            settings(tmp_path), http, Mealie(), SlugQueue(), selector=Selector()
        )
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()
        original_publish = service.store.publish

        def publish(data):
            loop.call_soon_threadsafe(entered.set)
            if not release.wait(10):
                raise RuntimeError("test publication was not released")
            return original_publish(data)

        async def download(postal_code):
            return snapshot()

        service.store.publish = publish
        service.source.download = download
        assert service.trigger("manual")
        await entered.wait()
        closing = asyncio.create_task(service.close())
        for _ in range(20):
            await asyncio.sleep(0)
        try:
            assert not closing.done()
            with pytest.raises(RuntimeError, match="pricing"):
                PricingOwner(str(tmp_path))
        finally:
            release.set()
            await closing


async def test_context_qualified_ingredient_does_not_bypass_decisions(tmp_path):
    from mealie_enricher.pricing.service import PRICING_EXTRA, PricingService

    class AbstainingSelector(Selector):
        async def choose(self, recipe, ingredient, candidates, **kwargs):
            self.calls += 1
            return None

    mealie, selector = Mealie(), AbstainingSelector()
    mealie.recipe.recipe_ingredient[1].note = "ahumado"
    async with httpx.AsyncClient() as http:
        service = PricingService(settings(tmp_path), http, mealie, SlugQueue(), selector=selector)
        try:
            service.store.publish(snapshot())
            await service.process_slug("arroz-pollo")
            assert selector.calls == 1
            result = json.loads(mealie.recipe.extras[PRICING_EXTRA])["retailers"]["mercadona"]
            assert result["total_cost"] is None
        finally:
            await service.close()


async def test_remote_personal_edits_during_selection_are_preserved(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    mealie = Mealie()

    class EditingSelector(Selector):
        async def choose(self, recipe, ingredient, candidates, **kwargs):
            mealie.recipe.extras["during_selection"] = "keep"
            mealie.recipe.tags.append(MealieTag(id="added", name="Added", slug="added"))
            return candidates[0].id, 0.99

    async with httpx.AsyncClient() as http:
        service = PricingService(
            settings(tmp_path), http, mealie, SlugQueue(), selector=EditingSelector()
        )
        try:
            service.store.publish(snapshot(competitor=True))
            await service.process_slug("arroz-pollo")
            assert mealie.recipe.extras["during_selection"] == "keep"
            assert "Added" in {tag.name for tag in mealie.recipe.tags}
        finally:
            await service.close()


async def test_remote_ingredient_edit_during_selection_defers_stale_write(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    mealie = Mealie()

    class EditingSelector(Selector):
        async def choose(self, recipe, ingredient, candidates, **kwargs):
            mealie.recipe.recipe_ingredient[0].quantity = 999.0
            return candidates[0].id, 0.99

    async with httpx.AsyncClient() as http:
        service = PricingService(
            settings(tmp_path), http, mealie, SlugQueue(), selector=EditingSelector()
        )
        try:
            service.store.publish(snapshot(competitor=True))
            with pytest.raises(RuntimeError, match="changed"):
                await service.process_slug("arroz-pollo")
            assert mealie.patches == []
        finally:
            await service.close()


async def test_transient_decisions_failure_is_not_cached_as_abstention(tmp_path):
    from mealie_enricher.pricing.selection import SelectionUnavailable
    from mealie_enricher.pricing.service import PricingService

    class FlakySelector(Selector):
        async def choose(self, recipe, ingredient, candidates, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise SelectionUnavailable("temporary")
            return candidates[0].id, 0.99

    async with httpx.AsyncClient() as http:
        selector = FlakySelector()
        service = PricingService(settings(tmp_path), http, Mealie(), SlugQueue(), selector=selector)
        try:
            service.store.publish(snapshot(competitor=True))
            await service.refresh()
            assert service.state.data["pending_refresh"]
            await service.refresh()
            assert selector.calls == 2
            assert not service.state.data["pending_refresh"]
        finally:
            await service.close()


async def test_publication_waits_until_all_recipe_candidate_reads_finish(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    async with httpx.AsyncClient() as http:
        service = PricingService(
            settings(tmp_path), http, Mealie(), SlugQueue(), selector=Selector()
        )
        loop = asyncio.get_running_loop()
        reading, published = asyncio.Event(), asyncio.Event()
        release = threading.Event()
        first = True
        active = snapshot()

        class Catalog:
            def load(self, retailer, postal_code):
                return active

            def search(self, retailer, postal_code, name, limit):
                nonlocal first
                products = [p for p in active.products if p.name == name]
                if first:
                    first = False
                    loop.call_soon_threadsafe(reading.set)
                    release.wait(10)
                return products

            def publish(self, new):
                nonlocal active
                active = new
                loop.call_soon_threadsafe(published.set)
                return new.fingerprint

        async def download(postal_code):
            return snapshot(price="5.00")

        service.store = Catalog()
        service.source.download = download
        pricing = asyncio.create_task(service.process_slug("arroz-pollo"))
        await reading.wait()
        syncing = asyncio.create_task(service.sync())
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(published.wait(), 0.2)
        finally:
            release.set()
            await pricing
            await syncing
            await service.close()


async def test_volatile_mealie_reference_ids_do_not_invalidate_recipe_or_choices(tmp_path):
    from mealie_enricher.pricing.service import PricingService

    class VolatileMealie(Mealie):
        async def get_recipe(self, slug, household_id=None):
            current = await super().get_recipe(slug, household_id)
            current.model_extra["recipeInstructions"] = [
                {"id": str(uuid.uuid4()), "text": "Mezclar"}
            ]
            for line in current.recipe_ingredient:
                line.reference_id = str(uuid.uuid4())
            return current

    mealie, selector = VolatileMealie(), Selector()
    async with httpx.AsyncClient() as http:
        service = PricingService(settings(tmp_path), http, mealie, SlugQueue(), selector=selector)
        try:
            service.store.publish(snapshot())
            await service.process_slug("arroz-pollo")
            assert selector.calls == 2
            await service.process_slug("arroz-pollo")
            assert selector.calls == 2
            assert len(mealie.patches) == 1
        finally:
            await service.close()
