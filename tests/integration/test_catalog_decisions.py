import asyncio
import json

import httpx2
import pytest
from openai import AsyncOpenAI

from mealie_enricher.catalog.models import CatalogFood, CatalogQuery
from mealie_enricher.config import DecisionSettings

FOODS = [
    CatalogFood(id="bedca:raw", source="bedca", source_id="raw", name="Arroz crudo", state="raw"),
    CatalogFood(
        id="bedca:cooked", source="bedca", source_id="cooked", name="Arroz cocido", state="cooked"
    ),
]


def response(answer=None):
    return {
        "answers": [
            answer
            if answer is not None
            else {
                "type": "choice",
                "name": "food",
                "choice": "bedca:raw",
                "confidence": 0.98,
                "probabilities": [
                    {"value": "bedca:raw", "probability": 0.98},
                    {"value": "bedca:cooked", "probability": 0.01},
                    {"value": "needs_context", "probability": 0.01},
                ],
            }
        ],
        "model": "gpt-6-luna",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 1,
            "total_tokens": 11,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def selector(handler, **settings):
    from mealie_enricher.agents.catalog_decisions import OpenAIDecisionSelector

    client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    config = DecisionSettings(enabled=True, api_key="test-key", **settings)
    return OpenAIDecisionSelector(config, client=client)


async def test_official_decisions_request_restricts_choices_and_keeps_context():
    def handler(request):
        assert request.url.path == "/v1/decisions"
        body = json.loads(request.content)
        assert body["model"] == "gpt-6-luna"
        context = json.loads(body["input"])
        assert context["food_name"] == "Arroz"
        assert context["note"] == "para la sopa"
        assert context["instructions"] == "Añadir el arroz y hervir"
        question = body["questions"][0]
        assert question["type"] == "choice"
        assert question["name"] == "food"
        assert {item["value"] for item in question["choices"]} == {
            "bedca:raw",
            "bedca:cooked",
            "needs_context",
        }
        return httpx2.Response(200, json=response())

    service = selector(handler)
    try:
        result = await service.choose(
            CatalogQuery(
                food_name="Arroz", note="para la sopa", instructions="Añadir el arroz y hervir"
            ),
            FOODS,
        )
        assert result == ("bedca:raw", 0.98)
    finally:
        await service.close()


@pytest.mark.parametrize(
    "answer",
    [
        {"type": "refusal", "name": "food"},
        {"type": "predicate", "name": "food", "probability": 0.99},
        {
            "type": "choice",
            "name": "food",
            "choice": "needs_context",
            "confidence": 0.99,
            "probabilities": [],
        },
        {
            "type": "choice",
            "name": "food",
            "choice": "not-offered",
            "confidence": 0.99,
            "probabilities": [],
        },
        {
            "type": "choice",
            "name": "food",
            "choice": "bedca:raw",
            "confidence": 0.89,
            "probabilities": [],
        },
        {"type": "choice", "name": "food", "choice": "bedca:raw", "probabilities": []},
        {
            "type": "choice",
            "name": "food",
            "choice": "bedca:raw",
            "confidence": 1.5,
            "probabilities": [],
        },
        {
            "type": "choice",
            "name": "unrelated",
            "choice": "bedca:raw",
            "confidence": 0.99,
            "probabilities": [],
        },
    ],
)
async def test_refused_malformed_unoffered_or_low_confidence_answers_abstain(answer):
    service = selector(lambda request: httpx2.Response(200, json=response(answer)))
    try:
        assert await service.choose(CatalogQuery(food_name="Arroz"), FOODS) is None
    finally:
        await service.close()


@pytest.mark.parametrize("answers", [[], [{"type": "refusal"}, {"type": "refusal"}]])
async def test_missing_or_multiple_answers_abstain(answers):
    payload = response()
    payload["answers"] = answers
    service = selector(lambda request: httpx2.Response(200, json=payload))
    try:
        assert await service.choose(CatalogQuery(food_name="Arroz"), FOODS) is None
    finally:
        await service.close()


async def test_provider_failure_does_not_retry_or_log_sensitive_body(caplog):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx2.Response(500, json={"error": {"message": "secret-provider-body-test-key"}})

    service = selector(handler)
    try:
        assert await service.choose(CatalogQuery(food_name="Arroz"), FOODS) is None
        assert calls == 1
        assert "secret-provider-body" not in caplog.text
        assert "test-key" not in caplog.text
        assert "InternalServerError" in caplog.text
    finally:
        await service.close()


async def test_selector_timeout_covers_waiting_and_external_call():
    async def handler(request):
        await asyncio.sleep(0.1)
        return httpx2.Response(200, json=response())

    service = selector(handler, timeout_seconds=0.01, max_concurrency=1)
    try:
        results = await asyncio.gather(
            *[service.choose(CatalogQuery(food_name="Arroz"), FOODS) for _ in range(3)]
        )
        assert results == [None, None, None]
    finally:
        await service.close()


async def test_selector_bounds_batch_concurrency():
    active = 0
    maximum = 0

    async def handler(request):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx2.Response(200, json=response())

    service = selector(handler, max_concurrency=2)
    try:
        results = await asyncio.gather(
            *[service.choose(CatalogQuery(food_name="Arroz"), FOODS) for _ in range(6)]
        )
        assert results == [("bedca:raw", 0.98)] * 6
        assert maximum == 2
    finally:
        await service.close()


@pytest.mark.parametrize(
    "foods",
    [
        [],
        [FOODS[0], FOODS[0]],
        [
            FOODS[0].model_copy(update={"id": "needs_context"}),
        ],
        [FOODS[0].model_copy(update={"id": str(index)}) for index in range(255)],
    ],
)
async def test_invalid_candidate_sets_abstain_without_external_work(foods):
    def unexpected(request):
        pytest.fail("Invalid candidates must not trigger a paid request")

    service = selector(unexpected)
    try:
        assert await service.choose(CatalogQuery(food_name="Arroz"), foods) is None
    finally:
        await service.close()


async def test_enabled_selector_requires_credentials_and_disabled_selector_does_no_work():
    from mealie_enricher.agents.catalog_decisions import OpenAIDecisionSelector

    with pytest.raises(ValueError, match="API key"):
        OpenAIDecisionSelector(DecisionSettings(enabled=True))
    service = OpenAIDecisionSelector(DecisionSettings(enabled=False))
    assert await service.choose(CatalogQuery(food_name="Arroz"), FOODS) is None
    await service.close()


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -0.1, True])
async def test_nonfinite_or_nonprobability_confidence_abstains(confidence):
    payload = response()
    payload["answers"][0]["confidence"] = confidence
    service = selector(lambda request: httpx2.Response(200, content=json.dumps(payload)))
    try:
        assert await service.choose(CatalogQuery(food_name="Arroz"), FOODS) is None
    finally:
        await service.close()


async def test_selector_signature_ignores_secret_but_tracks_model_and_confidence():
    from mealie_enricher.agents.catalog_decisions import OpenAIDecisionSelector

    services = [
        OpenAIDecisionSelector(settings)
        for settings in [
            DecisionSettings(enabled=False, api_key="secret-one"),
            DecisionSettings(enabled=False, api_key="secret-two"),
            DecisionSettings(enabled=False, min_confidence=0.95),
            DecisionSettings(enabled=False, model="future-choice-model"),
        ]
    ]
    assert services[0].signature == services[1].signature
    assert services[0].signature != services[2].signature
    assert services[0].signature != services[3].signature
    assert "secret-one" not in services[0].signature
    for service in services:
        await service.close()
