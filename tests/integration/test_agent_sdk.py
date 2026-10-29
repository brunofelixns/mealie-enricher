import json

import httpx
import pytest
import respx

from mealie_enricher.agents.estimator_agent import AgentLlmRunner
from mealie_enricher.config import LlmSettings


@pytest.mark.parametrize("status", [200, 429, 500])
async def test_real_runner_preserves_single_request_and_custom_endpoint(status):
    settings = LlmSettings(
        enabled=True,
        api_key="synthetic",
        base_url="https://llm.test/v1",
        endpoint_url="/custom",
        model="configured-model",
    )
    with respx.mock(assert_all_called=False) as router:
        route = router.post("https://llm.test/v1/custom").mock(
            return_value=httpx.Response(status, json={"choices": [{"message": {"content": "80"}}]})
        )
        traces = router.route(host="api.openai.com").mock(return_value=httpx.Response(200))
        async with httpx.AsyncClient() as client:
            result = await AgentLlmRunner(settings, client).complete("same prompt", max_tokens=10)
        assert result == ("80" if status == 200 else None)
        assert route.call_count == 1
        assert traces.call_count == 0
        request = route.calls[0].request
        assert request.headers["authorization"] == "Bearer synthetic"
        assert json.loads(request.content) == {
            "model": "configured-model",
            "messages": [{"role": "user", "content": "same prompt"}],
            "temperature": 0.1,
            "max_tokens": 10,
        }


@pytest.mark.parametrize("enabled,key", [(False, "synthetic"), (True, "")])
async def test_disabled_or_missing_key_never_contacts_provider(enabled, key):
    with respx.mock as router:
        async with httpx.AsyncClient() as client:
            result = await AgentLlmRunner(
                LlmSettings(enabled=enabled, api_key=key), client
            ).complete("prompt", max_tokens=10)
        assert result is None
        assert not router.calls


@pytest.mark.parametrize("data", [{}, {"choices": []}, {"choices": [{"message": {}}]}])
async def test_incomplete_provider_response_returns_unknown_without_retry(data):
    with respx.mock as router:
        route = router.post("https://llm.test/chat/completions").mock(
            return_value=httpx.Response(200, json=data)
        )
        async with httpx.AsyncClient() as client:
            runner = AgentLlmRunner(
                LlmSettings(enabled=True, api_key="synthetic", base_url="https://llm.test"),
                client,
            )
            assert await runner.complete("prompt", max_tokens=10) is None
        assert route.call_count == 1
