import json

import httpx
import pytest
import respx

from mealie_enricher.agents.estimator_agent import AgentLlmRunner
from mealie_enricher.config import LlmSettings, load_settings


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


@pytest.mark.parametrize("model", ["gpt-5-mini", "gpt-6.1-sol", "gpt-6.1-sol-2026-10-20", "o3"])
async def test_reasoning_models_estimate_without_unsupported_parameters(model):
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "synthetic",
            "LLM_ENABLED": "true",
            "LLM_API_KEY": "synthetic",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_MODEL": model,
        }
    ).llm

    def respond(request):
        payload = json.loads(request.content)
        if "max_tokens" in payload or "temperature" in payload:
            return httpx.Response(400, json={"error": {"code": "unsupported_parameter"}})
        if payload.get("max_completion_tokens", 0) < 1024:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "14"}, "finish_reason": "stop"}]}
        )

    with respx.mock as router:
        route = router.post("https://api.openai.com/v1/chat/completions").mock(side_effect=respond)
        async with httpx.AsyncClient() as client:
            result = await AgentLlmRunner(settings, client).complete(
                "Estimate one tablespoon of olive oil in grams.",
                max_tokens=int(settings.max_tokens_grams),
            )
        assert result == "14"
        assert route.call_count == 1
        assert json.loads(route.calls[0].request.content)["model"] == model


@pytest.mark.parametrize("model", ["gpt-4o-mini", "mistral-small-latest", "gpt-5-chat-latest"])
async def test_non_reasoning_models_keep_configured_temperature_and_token_limit(model):
    with respx.mock as router:
        route = router.post("https://llm.test/chat/completions").respond(
            200, json={"choices": [{"message": {"content": "80"}}]}
        )
        async with httpx.AsyncClient() as client:
            result = await AgentLlmRunner(
                LlmSettings(
                    enabled=True,
                    api_key="synthetic",
                    base_url="https://llm.test",
                    model=model,
                    temperature=0.25,
                ),
                client,
            ).complete("prompt", max_tokens=20)
        assert result == "80"
        assert json.loads(route.calls[0].request.content) == {
            "model": model,
            "messages": [{"role": "user", "content": "prompt"}],
            "temperature": 0.25,
            "max_tokens": 20,
        }


async def test_http_failure_logs_provider_reason_and_model_without_credentials(caplog):
    secret = "synthetic-private-credential"
    with respx.mock as router:
        route = router.post("https://llm.test/chat/completions").respond(
            400,
            headers={"x-request-id": "req-test-400"},
            json={
                "error": {
                    "message": f"Unsupported max_tokens. Credential: {secret}",
                    "code": "unsupported_parameter",
                    "param": "max_tokens",
                }
            },
        )
        async with httpx.AsyncClient() as client:
            result = await AgentLlmRunner(
                LlmSettings(
                    enabled=True, api_key=secret, base_url="https://llm.test", model="gpt-6.1-sol"
                ),
                client,
            ).complete("prompt", max_tokens=1024)
        assert result is None
        assert route.call_count == 1
    assert "400" in caplog.text
    assert "gpt-6.1-sol" in caplog.text
    assert "unsupported_parameter" in caplog.text
    assert "max_tokens" in caplog.text
    assert "req-test-400" in caplog.text
    assert secret not in caplog.text


@pytest.mark.parametrize("content", ["", "1", '{"kcal":2'])
async def test_truncated_response_is_not_used_as_an_estimate(content, caplog):
    with respx.mock as router:
        route = router.post("https://llm.test/chat/completions").respond(
            200,
            json={"choices": [{"message": {"content": content}, "finish_reason": "length"}]},
        )
        async with httpx.AsyncClient() as client:
            result = await AgentLlmRunner(
                LlmSettings(enabled=True, api_key="synthetic", base_url="https://llm.test"),
                client,
            ).complete("prompt", max_tokens=10)
        assert result is None
        assert route.call_count == 1
    assert "LLM_MAX_TOKENS" in caplog.text
