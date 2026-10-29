import httpx

from mealie_enricher.clients.open_food_facts import OffClient
from mealie_enricher.config import LlmSettings, OffSettings
from mealie_enricher.runtime.rate_limiter import RateLimiter
from tests.support.mock_off_server import search_response


async def test_mock_off_uses_current_search_hits_shape(cache):
    settings = OffSettings(search_base_url="http://mock-off.test")

    async def respond(request):
        return httpx.Response(200, json=search_response(request.url.params.get("q", "")))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        off = OffClient(settings, http, cache, RateLimiter(settings, LlmSettings()))
        result = await off.lookup_nutrients("mehl", "g")
        assert result.matched
        assert result.nutrients.kcal_per100g == 364
        assert not (await off.lookup_nutrients("no-match", "g")).matched
