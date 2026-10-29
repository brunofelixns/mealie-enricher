import json

import httpx
import pytest
import respx

from mealie_enricher.agents.estimator_agent import AgentLlmRunner
from mealie_enricher.agents.prompts import build_grams_prompt, build_nutrients_prompt
from mealie_enricher.config import load_settings
from tests.parity.cases import cases_for


@pytest.mark.parametrize("case", cases_for("llm"), ids=lambda case: case["id"])
async def test_sdk_transport_matches_original_request(case):
    expected = case["expected_requests"][0]
    external = case["external_responses"][0]
    settings = load_settings(case["environment"])
    data = case["input"]
    if "unit_name" in data:
        prompt = build_grams_prompt(data["unit_name"], data["food_name"])
        limit = settings.llm.max_tokens_grams
    else:
        prompt = build_nutrients_prompt(data["food_name"])
        limit = settings.llm.max_tokens_nutrients
    with respx.mock as router:
        route = router.post(expected["url"]).mock(
            return_value=httpx.Response(external["status"], json=external["json"])
        )
        async with httpx.AsyncClient() as client:
            await AgentLlmRunner(settings.llm, client).complete(prompt, max_tokens=int(limit))
        assert route.call_count == 1
        assert json.loads(route.calls[0].request.content) == expected["json"]
