import httpx
import pytest
import respx

from mealie_enricher.clients.open_food_facts import OffClient
from mealie_enricher.config import load_settings
from mealie_enricher.runtime.rate_limiter import RateLimiter
from tests.parity.cases import cases_for


@pytest.mark.parametrize("case", cases_for("off"), ids=lambda case: case["id"])
async def test_off_matches_reference_requests_retries_and_values(case, cache):
    settings = load_settings(case["environment"])
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    external = list(case["external_responses"])
    with respx.mock as router:
        route = router.get(case["expected_requests"][0]["url"]).mock(
            side_effect=lambda request: httpx.Response(
                external[0]["status"], json=external.pop(0)["json"]
            )
        )
        async with httpx.AsyncClient() as http:
            off = OffClient(
                settings.off, http, cache, RateLimiter(settings.off, settings.llm), sleep=sleep
            )
            actual = await off.lookup_nutrients(
                case["input"]["food_name"], case["input"].get("unit_name")
            )
        assert actual.model_dump(by_alias=True) == case["expected_result"]
        assert route.call_count == len(case["expected_requests"])
        assert waits == ([0.5, 1, 2] if case["id"] == "off-retries" else [])
