import asyncio
import json
from decimal import Decimal

import httpx2
import pytest
from openai import AsyncOpenAI

from mealie_enricher.config import DecisionSettings
from mealie_enricher.models import MealieRecipe
from mealie_enricher.pricing.models import Product

RECIPE = MealieRecipe.model_validate(
    {
        "slug": "rice",
        "name": "Arroz al horno",
        "recipeServings": 2,
        "recipeIngredient": [
            {
                "quantity": 200,
                "unit": {"name": "g"},
                "food": {"name": "Arroz crudo"},
                "note": "para hervir",
            }
        ],
        "recipeInstructions": [{"text": "Añadir el arroz crudo y hervir."}],
    }
)
PRODUCTS = [
    Product(
        id="rice-plain",
        name="Arroz crudo",
        price="1.50",
        package_quantity="1000",
        package_unit="g",
        ingredients="Arroz",
        nutrition={"sugars": "0.5"},
        raw={"observed_at": "2026-11-03", "secret": "not-evidence"},
    ),
    Product(
        id="rice-cooked",
        name="Arroz cocido con salsa",
        price="1.20",
        package_quantity="200",
        package_unit="g",
        ingredients="Arroz, agua, sal, aceite",
    ),
]


def response(answer=None):
    return {
        "answers": [
            answer
            if answer is not None
            else {
                "type": "choice",
                "name": "product",
                "choice": "rice-plain",
                "confidence": 0.98,
                "probabilities": [
                    {"value": "rice-plain", "probability": 0.98},
                    {"value": "rice-cooked", "probability": 0.01},
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
    from mealie_enricher.pricing.selection import ProductSelector

    client = AsyncOpenAI(
        api_key="synthetic-test-key",
        base_url="https://example.invalid/v1",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return ProductSelector(
        DecisionSettings(enabled=True, api_key="synthetic-test-key", **settings), client=client
    )


async def test_request_restricts_ids_and_uses_only_supplied_recipe_and_product_evidence():
    def handler(request):
        assert request.url.path == "/v1/decisions"
        body = json.loads(request.content)
        assert body["model"] == "gpt-6-luna"
        context = json.loads(body["input"])
        assert context["recipe"]["name"] == "Arroz al horno"
        assert "Añadir el arroz crudo" in json.dumps(
            context["recipe"]["instructions"], ensure_ascii=False
        )
        assert context["ingredient"]["food"]["name"] == "Arroz crudo"
        assert context["ingredient"]["quantity"] == 200.0
        question = body["questions"][0]
        assert question["name"] == "product"
        choices = question["choices"]
        assert {item["value"] for item in choices} == {"rice-plain", "rice-cooked", "needs_context"}
        evidence = json.loads(choices[0]["description"])
        assert evidence["price"] == "1.50"
        assert evidence["ingredients"] == "Arroz"
        assert evidence["nutrition"] == {"sugars": "0.5"}
        assert "observed_at" not in request.content.decode()
        assert "not-evidence" not in request.content.decode()
        assert "needs_context" in question["instructions"]
        return httpx2.Response(200, json=response())

    service = selector(handler)
    try:
        assert await service.choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS) == (
            "rice-plain",
            0.98,
        )
    finally:
        await service.close()


@pytest.mark.parametrize(
    "answer",
    [
        {"type": "refusal", "name": "product"},
        {"type": "choice", "name": "food", "choice": "rice-plain", "confidence": 0.99},
        {"type": "predicate", "name": "product", "choice": "rice-plain", "confidence": 0.99},
        {"type": "choice", "name": "product", "choice": "needs_context", "confidence": 0.99},
        {"type": "choice", "name": "product", "choice": "not-offered", "confidence": 0.99},
        {"type": "choice", "name": "product", "choice": 123, "confidence": 0.99},
        {"type": "choice", "name": "product", "choice": "rice-plain"},
    ]
    + [
        {"type": "choice", "name": "product", "choice": "rice-plain", "confidence": confidence}
        for confidence in [True, "0.99", None, float("nan"), float("inf"), -0.1, 0.89, 1.1]
    ],
)
async def test_invalid_or_uncertain_answers_abstain_without_coercion(answer):
    service = selector(lambda request: httpx2.Response(200, content=json.dumps(response(answer))))
    try:
        assert await service.choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS) is None
    finally:
        await service.close()


@pytest.mark.parametrize(
    "payload", [[], {}, {"answers": []}, {"answers": [None]}, {"answers": [{}, {}]}]
)
async def test_malformed_envelopes_abstain(payload):
    service = selector(lambda request: httpx2.Response(200, json=payload))
    try:
        assert await service.choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS) is None
    finally:
        await service.close()


async def test_unavailable_choice_is_rejected_even_when_provider_confidence_is_high():
    service = selector(lambda request: httpx2.Response(200, json=response()))
    try:
        unavailable = [PRODUCTS[0].model_copy(update={"available": False}), PRODUCTS[1]]
        assert await service.choose(RECIPE, RECIPE.recipe_ingredient[0], unavailable) is None
    finally:
        await service.close()


@pytest.mark.parametrize(
    "products",
    [
        [],
        [PRODUCTS[0], PRODUCTS[0]],
        [PRODUCTS[0].model_copy(update={"id": "needs_context"})],
        [PRODUCTS[0].model_copy(update={"id": str(index)}) for index in range(255)],
        [PRODUCTS[0].model_copy(update={"ingredients": "x" * 100_000})],
    ],
)
async def test_invalid_or_oversized_candidate_sets_never_make_external_requests(products):
    def unexpected(request):
        pytest.fail("Invalid candidates must not trigger a paid request")

    service = selector(unexpected)
    try:
        assert await service.choose(RECIPE, RECIPE.recipe_ingredient[0], products) is None
    finally:
        await service.close()


async def test_provider_errors_make_one_attempt_and_never_log_response_body_or_key(caplog):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx2.Response(
            500, json={"error": {"message": "private-provider-body-synthetic-test-key"}}
        )

    service = selector(handler)
    try:
        assert await service.choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS) is None
        assert calls == 1
        assert "private-provider-body" not in caplog.text
        assert "synthetic-test-key" not in caplog.text
        assert "InternalServerError" in caplog.text
    finally:
        await service.close()


@pytest.mark.parametrize("status", [429, 500, 503])
@pytest.mark.parametrize("raise_transient", [False, True])
async def test_transient_http_failures_can_be_propagated_without_response_details(
    status, raise_transient, caplog
):
    from mealie_enricher.pricing.selection import SelectionUnavailable

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx2.Response(
            status, json={"error": {"message": "private-provider-body-synthetic-test-key"}}
        )

    service = selector(handler)
    try:
        if raise_transient:
            with pytest.raises(SelectionUnavailable) as raised:
                await service.choose(
                    RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS, raise_transient=True
                )
            assert raised.value.__suppress_context__ is True
            assert "private-provider-body" not in str(raised.value)
            assert "synthetic-test-key" not in str(raised.value)
        else:
            assert await service.choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS) is None
        assert calls == 1
        assert "private-provider-body" not in caplog.text
        assert "synthetic-test-key" not in caplog.text
    finally:
        await service.close()


@pytest.mark.parametrize("transport_error", [httpx2.ConnectError, httpx2.ReadTimeout])
@pytest.mark.parametrize("raise_transient", [False, True])
async def test_transport_failures_can_be_propagated_without_private_error_message(
    transport_error, raise_transient, caplog
):
    from mealie_enricher.pricing.selection import SelectionUnavailable

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise transport_error("private-network-message-synthetic-test-key", request=request)

    service = selector(handler)
    try:
        if raise_transient:
            with pytest.raises(SelectionUnavailable) as raised:
                await service.choose(
                    RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS, raise_transient=True
                )
            assert raised.value.__suppress_context__ is True
            assert "private-network-message" not in str(raised.value)
            assert "synthetic-test-key" not in str(raised.value)
        else:
            assert await service.choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS) is None
        assert calls == 1
        assert "private-network-message" not in caplog.text
        assert "synthetic-test-key" not in caplog.text
    finally:
        await service.close()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 409, 422])
async def test_nontransient_http_failures_remain_abstentions_with_opt_in(status):
    service = selector(
        lambda request: httpx2.Response(status, json={"error": {"message": "invalid request"}})
    )
    try:
        assert (
            await service.choose(
                RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS, raise_transient=True
            )
            is None
        )
    finally:
        await service.close()


@pytest.mark.parametrize(
    "answer",
    [
        {"type": "refusal", "name": "product"},
        {"type": "choice", "name": "product", "choice": "needs_context", "confidence": 0.99},
        {"type": "choice", "name": "product", "choice": "rice-plain", "confidence": 0.8},
        {"type": "choice", "name": "product", "choice": "not-offered", "confidence": 0.99},
    ],
)
async def test_semantic_abstentions_remain_none_with_transient_propagation_enabled(answer):
    service = selector(lambda request: httpx2.Response(200, json=response(answer)))
    try:
        assert (
            await service.choose(
                RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS, raise_transient=True
            )
            is None
        )
    finally:
        await service.close()


async def test_opt_in_timeout_propagates_for_provider_and_waiting_concurrent_requests():
    from mealie_enricher.pricing.selection import SelectionUnavailable

    async def handler(request):
        await asyncio.Event().wait()
        pytest.fail("Timed out provider request must have been cancelled")

    service = selector(handler, timeout_seconds=0.01, max_concurrency=1)
    try:
        tasks = [
            service.choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS, raise_transient=True)
            for _ in range(3)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(result, SelectionUnavailable) for result in results)
        assert all(result.__suppress_context__ for result in results)
    finally:
        await service.close()


async def test_timeout_covers_waiting_for_concurrency_slot():
    async def handler(request):
        await asyncio.sleep(0.1)
        return httpx2.Response(200, json=response())

    service = selector(handler, timeout_seconds=0.01, max_concurrency=1)
    try:
        tasks = [service.choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS) for _ in range(3)]
        assert await asyncio.gather(*tasks) == [None, None, None]
    finally:
        await service.close()


async def test_concurrency_is_bounded():
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
        tasks = [service.choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS) for _ in range(6)]
        assert await asyncio.gather(*tasks) == [("rice-plain", 0.98)] * 6
        assert maximum == 2
    finally:
        await service.close()


async def test_signature_tracks_policy_settings_without_credentials_and_disabled_never_calls():
    from mealie_enricher.pricing.selection import ProductSelector

    services = [
        ProductSelector(config)
        for config in [
            DecisionSettings(api_key="secret-one"),
            DecisionSettings(api_key="secret-two"),
            DecisionSettings(model="future-model"),
            DecisionSettings(min_confidence=0.95),
        ]
    ]
    try:
        assert services[0].signature == services[1].signature
        assert services[0].signature != services[2].signature
        assert services[0].signature != services[3].signature
        assert "secret-one" not in services[0].signature
        assert await services[0].choose(RECIPE, RECIPE.recipe_ingredient[0], PRODUCTS) is None
        with pytest.raises(ValueError, match="API key"):
            ProductSelector(DecisionSettings(enabled=True))
    finally:
        for service in services:
            await service.close()


async def test_evidence_tracks_price_composition_and_new_products_but_not_observation_metadata():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=response())

    service = selector(handler)
    try:
        candidate_sets = [
            PRODUCTS,
            [PRODUCTS[0].model_copy(update={"raw": {"observed_at": "later"}}), PRODUCTS[1]],
            [PRODUCTS[0].model_copy(update={"price": Decimal("1.60")}), PRODUCTS[1]],
            [PRODUCTS[0].model_copy(update={"ingredients": "Arroz, sal"}), PRODUCTS[1]],
            [*PRODUCTS, PRODUCTS[0].model_copy(update={"id": "new-product"})],
        ]
        for candidates in candidate_sets:
            await service.choose(RECIPE, RECIPE.recipe_ingredient[0], candidates)
        assert requests[0] == requests[1]
        assert requests[0] != requests[2]
        assert requests[0] != requests[3]
        assert requests[0] != requests[4]
    finally:
        await service.close()
