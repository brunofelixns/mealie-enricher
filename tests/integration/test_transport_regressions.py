import asyncio
import json

import httpx
import pytest
import respx

from mealie_enricher.agents.estimator_agent import AgentLlmRunner
from mealie_enricher.clients.open_food_facts import OffClient
from mealie_enricher.config import LlmSettings, MealieSettings, OffSettings
from mealie_enricher.runtime.rate_limiter import RateLimiter
from mealie_enricher.services.mealie_theme import DEFAULT_THEME, MealieThemeClient
from tests.support.mock_off_server import search_response


@pytest.mark.parametrize("status", [307, 308])
async def test_sdk_follows_fetch_redirect_with_same_payload(status):
    settings = LlmSettings(
        enabled=True,
        api_key="synthetic",
        base_url="https://llm.test/v1",
        endpoint_url="/custom",
        model="test-model",
    )
    with respx.mock as mock:
        first = mock.post("https://llm.test/v1/custom").respond(
            status, headers={"Location": "/canonical"}
        )
        final = mock.post("https://llm.test/canonical").respond(
            200, json={"choices": [{"message": {"content": "80"}}]}
        )
        async with httpx.AsyncClient() as http:
            result = await AgentLlmRunner(settings, http).complete("prompt", max_tokens=10)
        assert result == "80"
        assert first.call_count == final.call_count == 1
        assert json.loads(first.calls.last.request.content) == json.loads(
            final.calls.last.request.content
        )


async def test_off_and_theme_follow_fetch_redirects(cache):
    off_settings, llm_settings = OffSettings(search_base_url="https://off.test"), LlmSettings()
    with respx.mock as mock:
        mock.get(url__startswith="https://off.test/search?").respond(
            302, headers={"Location": "/canonical"}
        )
        mock.get("https://off.test/canonical").respond(200, json=search_response("mehl"))
        mock.get("https://mealie.test/api/app/about/theme").respond(
            301, headers={"Location": "/theme"}
        )
        mock.get("https://mealie.test/theme").respond(200, json={"lightPrimary": "#123456"})
        async with httpx.AsyncClient() as http:
            off = OffClient(off_settings, http, cache, RateLimiter(off_settings, llm_settings))
            assert (await off.lookup_nutrients("mehl")).matched
            theme = MealieThemeClient(MealieSettings(url="https://mealie.test"), http)
            assert (await theme.get_theme()).light.primary == "#123456"


async def test_theme_timeout_covers_entire_stream():
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            for chunk in [b'{"lightPrimary":', b'"#123456"', b"}"]:
                await asyncio.sleep(0.015)
                yield chunk

    async def respond(request):
        return httpx.Response(200, stream=SlowBody())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        theme = MealieThemeClient(MealieSettings(url="https://mealie.test", timeout_ms=25), http)
        assert await theme.get_theme() == DEFAULT_THEME
