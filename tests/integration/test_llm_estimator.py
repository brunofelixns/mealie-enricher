import httpx
import pytest
import respx

from mealie_enricher.agents.estimator_agent import AgentLlmRunner
from mealie_enricher.config import load_settings
from mealie_enricher.runtime.rate_limiter import RateLimiter
from mealie_enricher.services.llm_estimator import LlmEstimator
from tests.parity.cases import cases_for


@pytest.mark.parametrize("case", cases_for("llm"), ids=lambda case: case["id"])
async def test_fallback_parsers_match_executed_original(case, cache):
    settings = load_settings(case["environment"])
    data = case["input"]
    external = case["external_responses"][0]
    with respx.mock as router:
        route = router.post(case["expected_requests"][0]["url"]).respond(
            external["status"], json=external["json"]
        )
        async with httpx.AsyncClient() as http:
            llm = LlmEstimator(
                settings.llm,
                AgentLlmRunner(settings.llm, http),
                cache,
                RateLimiter(settings.off, settings.llm),
            )
            if "unit_name" in data:
                result = await llm.estimate_grams(
                    data["quantity"], data["unit_name"], data["food_name"]
                )
            else:
                result = await llm.estimate_nutrients(data["food_name"])
                if result is not None:
                    result = result.model_dump(by_alias=True)
        assert result == case["expected_result"]
        assert route.call_count == 1
