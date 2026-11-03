import asyncio
import json

import httpx2
import pytest
from openai import AsyncOpenAI

from mealie_enricher.config import DecisionSettings
from mealie_enricher.models import MealieRecipe


def recipe(**updates):
    return MealieRecipe.model_validate(
        {
            "slug": "ensalada",
            "name": "Ensalada casera",
            "recipeIngredient": [
                {"food": {"name": "Tomate"}, "originalText": "2 tomates"},
                {"originalText": "1 cucharada de aceite de oliva"},
            ],
            "recipeInstructions": [{"text": "Cortar y aliñar"}],
            **updates,
        }
    )


def response(**updates):
    return {
        "answers": [
            {
                "type": "choice",
                "name": "nova",
                "choice": "nova_1",
                "confidence": 0.98,
                "probabilities": [
                    {"value": "nova_1", "probability": 0.98},
                    {"value": "nova_2", "probability": 0.005},
                    {"value": "nova_3", "probability": 0.005},
                    {"value": "nova_4", "probability": 0.005},
                    {"value": "needs_context", "probability": 0.005},
                ],
                **updates,
            }
        ]
    }


def classifier(handler, **settings):
    from mealie_enricher.agents.nova_decisions import OpenAINovaClassifier

    client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return OpenAINovaClassifier(DecisionSettings(api_key="test-key", **settings), client=client)


@pytest.mark.parametrize("group", [1, 2, 3, 4])
async def test_decisions_sends_recipe_evidence_and_accepts_only_offered_nova_groups(group):
    def handler(request):
        assert request.url.path == "/v1/decisions"
        body = json.loads(request.content)
        assert body["model"] == "gpt-6-luna"
        evidence = json.loads(body["input"])
        assert evidence["ingredients"][1]["originalText"] == "1 cucharada de aceite de oliva"
        assert evidence["instructions"] == [{"text": "Cortar y aliñar"}]
        assert "tags" not in evidence
        assert "extras" not in evidence
        question = body["questions"][0]
        assert question["type"] == "choice"
        assert question["name"] == "nova"
        assert {choice["value"] for choice in question["choices"]} == {
            "nova_1",
            "nova_2",
            "nova_3",
            "nova_4",
            "needs_context",
        }
        return httpx2.Response(200, json=response(choice=f"nova_{group}"))

    service = classifier(handler)
    try:
        result = await service.classify(recipe())
        assert result.group == group
        assert result.tag == f"NOVA:{group}"
        assert result.confidence == 0.98
        assert result.status == "classified"
    finally:
        await service.close()


@pytest.mark.parametrize(
    "updates",
    [
        {"choice": "needs_context"},
        {"choice": "nova_9"},
        {"choice": True},
        {"type": "refusal"},
        {"type": "score"},
        {"name": "food"},
        {"confidence": None},
        {"confidence": True},
        {"confidence": "0.99"},
        {"confidence": float("nan")},
        {"confidence": float("inf")},
        {"confidence": 0.89},
        {"confidence": 1.01},
    ],
)
async def test_uncertain_refused_or_invalid_answers_produce_unknown(updates):
    # Allow nonfinite JSON to exercise the raw-response validator.
    payload = json.dumps(response(**updates))
    service = classifier(lambda request: httpx2.Response(200, content=payload))
    try:
        result = await service.classify(recipe())
        assert result.group is None
        assert result.tag == "NOVA:Desconocida"
        assert result.status != "classified"
    finally:
        await service.close()


@pytest.mark.parametrize("answers", [None, [], [{}, {}], [None]])
async def test_malformed_answer_envelopes_produce_unknown(answers):
    service = classifier(lambda request: httpx2.Response(200, json={"answers": answers}))
    try:
        assert (await service.classify(recipe())).tag == "NOVA:Desconocida"
    finally:
        await service.close()


async def test_provider_error_has_no_retries_and_does_not_log_response_body(caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(500, json={"error": {"message": "sensitive-provider-test-key"}})

    service = classifier(handler)
    try:
        result = await service.classify(recipe())
        assert result.tag == "NOVA:Desconocida"
        assert result.status == "error"
        assert len(calls) == 1
        assert "sensitive-provider" not in caplog.text
        assert "test-key" not in caplog.text
    finally:
        await service.close()


async def test_timeout_also_bounds_waiting_for_classifier_capacity():
    async def handler(request):
        await asyncio.sleep(0.1)
        return httpx2.Response(200, json=response())

    service = classifier(handler, timeout_seconds=0.01, max_concurrency=1)
    try:
        results = await asyncio.gather(*(service.classify(recipe()) for _ in range(3)))
        assert all(result.status == "error" for result in results)
    finally:
        await service.close()


@pytest.mark.parametrize("ingredients", [[], [{}], [{"originalText": "   "}]])
async def test_missing_ingredient_evidence_never_calls_provider(ingredients):
    def handler(request):
        pytest.fail("A title alone cannot establish NOVA")

    service = classifier(handler)
    try:
        result = await service.classify(recipe(recipeIngredient=ingredients))
        assert result.status == "no_ingredients"
        assert result.tag == "NOVA:Desconocida"
    finally:
        await service.close()


@pytest.mark.parametrize("choice", ["nova_1", "needs_context"])
async def test_cached_assessment_survives_tag_changes_but_not_evidence_or_config_changes(choice):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(200, json=response(choice=choice))

    service = classifier(handler)
    try:
        original = recipe()
        assessment = await service.classify(original)
        original.extras = {"calorie_estimator_nova": assessment.model_dump_json()}
        assert await service.classify(original) == assessment
        assert len(calls) == 1
        original.name = "Ensalada con queso"
        assert (await service.classify(original)).input_hash != assessment.input_hash
        assert len(calls) == 2
        await service.classify(original, force=True)
        assert len(calls) == 3
        service.settings.min_confidence = 0.99
        assert service.cached(original) is None
    finally:
        await service.close()
