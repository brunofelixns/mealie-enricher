"""Opt-in real Mealie HTTP boundary; owns only its random Compose project."""

import json
import os

import httpx
import pytest

from mealie_enricher.clients.mealie import MealieClient
from mealie_enricher.pricing.service import PRICING_EXTRA, PricingService
from mealie_enricher.runtime.slug_queue import SlugQueue
from tests.integration.test_pricing_service import Selector, settings, snapshot
from tests.support.mealie_stack import MealieStack

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PRICING_MEALIE_E2E") != "1",
    reason="Set RUN_PRICING_MEALIE_E2E=1 for isolated real Mealie pricing validation",
)


async def test_exact_price_tags_and_product_extras_on_real_mealie(tmp_path):
    stack = MealieStack(tmp_path)
    try:
        stack.save_env()
        stack.run("up", "-d", "--pull", "never", "--wait", "mealie")
        response = stack.mealie.post(
            "/api/users/register",
            json={
                "username": "pricing-e2e",
                "fullName": "Pricing E2E",
                "email": "pricing-e2e@example.test",
                "password": "Synthetic-pricing-42!",
                "passwordConfirm": "Synthetic-pricing-42!",
                "seedData": False,
                "group": "Pricing E2E",
            },
        )
        response.raise_for_status()
        login = stack.mealie.post(
            "/api/auth/token",
            data={"username": "pricing-e2e@example.test", "password": "Synthetic-pricing-42!"},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        stack.mealie.headers["Authorization"] = "Bearer " + token
        slug = stack.recipe(
            [
                stack.ingredient("Arroz", note="", quantity=500),
                stack.ingredient("Pollo", note="", quantity=600),
            ],
            servings=4,
            extras={"personal": "conservar"},
            nutrition={"calories": "321"},
        )
        config = settings(tmp_path / "pricing")
        config.mealie.url = str(stack.mealie.base_url)
        config.mealie.api_token = token
        async with httpx.AsyncClient(trust_env=False, timeout=20) as http:
            service = PricingService(
                config, http, MealieClient(config, http), SlugQueue(), selector=Selector()
            )
            try:
                service.store.publish(snapshot())
                await service.process_slug(slug)
                first = stack.get(slug)
                assert {"Mercadona:1,50 €/ración", "Mercadona:10,80 € compra"}.issubset(
                    {tag["name"] for tag in first["tags"]}
                )
                data = json.loads(first["extras"][PRICING_EXTRA])["retailers"]["mercadona"]
                assert data["total_cost"] == "6.00"
                assert first["nutrition"]["calories"] == "321"
                assert first["extras"]["personal"] == "conservar"
                service.store.publish(snapshot(price="5.00"))
                await service.process_slug(slug)
                second = stack.get(slug)
                assert "Mercadona:1,50 €/ración" not in {tag["name"] for tag in second["tags"]}
                assert "Mercadona:11,00 € compra" in {tag["name"] for tag in second["tags"]}
            finally:
                await service.close()
    finally:
        stack.close()
