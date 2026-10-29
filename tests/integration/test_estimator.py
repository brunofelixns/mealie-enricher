import httpx
import pytest
import respx

from mealie_enricher.agents.estimator_agent import AgentLlmRunner
from mealie_enricher.clients.open_food_facts import OffClient
from mealie_enricher.config import load_settings
from mealie_enricher.models import MealieRecipe
from mealie_enricher.runtime.rate_limiter import RateLimiter
from mealie_enricher.services.estimator import Estimator
from mealie_enricher.services.llm_estimator import LlmEstimator
from tests.parity.cases import cases_for

CASES = [c for c in cases_for("estimator") if c["id"].startswith("estimate-")]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
async def test_concurrent_estimation_matches_reference(case, cache):
    settings = load_settings(case["environment"])
    with respx.mock(assert_all_called=False) as router:
        if case["expected_requests"]:
            external = case["external_responses"][0]
            router.get(case["expected_requests"][0]["url"]).respond(
                external["status"], json=external["json"]
            )
        async with httpx.AsyncClient() as http:
            limiter = RateLimiter(settings.off, settings.llm)
            off = OffClient(settings.off, http, cache, limiter)
            llm = LlmEstimator(settings.llm, AgentLlmRunner(settings.llm, http), cache, limiter)
            result = await Estimator(off, llm).estimate_recipe(
                MealieRecipe.model_validate(case["input"])
            )
        assert (
            result.model_dump(by_alias=True, exclude_unset=True)
            == case["expected_result"]["result"]
        )
