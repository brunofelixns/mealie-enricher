"""HTTP workflows using real DuckDB/SQLite and the real, intercepted OpenAI SDK."""

import asyncio
import copy
import csv
import hashlib
import json
import sqlite3
from contextlib import asynccontextmanager, closing

import duckdb
import httpx
import httpx2
import pytest
from openai import AsyncOpenAI

from mealie_enricher.app import create_app
from mealie_enricher.catalog.bedca import import_bedca
from mealie_enricher.config import load_settings
from tests.integration.test_bedca_import import make_export
from tests.integration.test_catalog_decisions import response as decisions_response


class CatalogWorkflow:
    def __init__(self, tmp_path, monkeypatch):
        self.source = make_export(tmp_path / "source")
        self.catalog_path = tmp_path / "catalog.duckdb"
        self.cache_path = tmp_path / "cache.db"
        import_bedca(self.source, self.catalog_path, "synthetic-v1")
        self.settings = load_settings(
            {
                "MEALIE_API_TOKEN": "synthetic-mealie-token",
                "MEALIE_URL": "https://mealie.test",
                "CACHE_DB_PATH": str(self.cache_path),
                "CATALOG_ENABLED": "true",
                "CATALOG_DB_PATH": str(self.catalog_path),
                "DECISIONS_ENABLED": "true",
                "DECISIONS_API_KEY": "synthetic-decisions-key",
                "EVENT_DEBOUNCE_MS": "1",
            }
        )
        self.recipe = {
            "slug": "arroz",
            "name": "Sopa de arroz",
            "recipeServings": 2,
            "recipeInstructions": [{"text": "Pesar el arroz antes de añadirlo al agua."}],
            "recipeIngredient": [
                {
                    "quantity": 200,
                    "unit": {"name": "g"},
                    "food": {"name": "Arroz"},
                    "note": "para la sopa",
                }
            ],
            "nutrition": {"calories": "999"},
            "extras": {"calorie_estimator_hash": "previous-automatic-estimate"},
        }
        self.mode = "success"
        self.requests = []
        self.patches = []
        self.sdk_transports = []

        def sdk_factory(**kwargs):
            assert kwargs["api_key"] == "synthetic-decisions-key"
            transport = httpx2.AsyncClient(transport=httpx2.MockTransport(self.decide))
            self.sdk_transports.append(transport)
            return AsyncOpenAI(
                **kwargs,
                base_url="https://openai.test/v1",
                http_client=transport,
                organization="synthetic",
                project="synthetic",
            )

        monkeypatch.setattr(
            "mealie_enricher.agents.catalog_decisions.AsyncOpenAI",
            sdk_factory,
        )

    def decide(self, request):
        assert request.url.host == "openai.test"
        assert request.url.path == "/v1/decisions"
        self.requests.append(json.loads(request.content))
        if self.mode in {"401", "429"}:
            return httpx2.Response(
                int(self.mode),
                json={
                    "error": {
                        "message": "Synthetic provider failure",
                        "type": "invalid_request_error",
                    },
                },
            )
        if self.mode == "timeout":
            raise httpx2.ReadTimeout("Synthetic timeout", request=request)
        answer = {
            "type": "choice",
            "name": "food",
            "choice": "bedca:1",
            "confidence": 0.99,
            "probabilities": [{"value": "bedca:1", "probability": 0.99}],
            # Even an extra generated number must never become nutritional truth.
            "nutrients": {"kcal_per100g": 123456},
        }
        if self.mode == "needs_context":
            answer["choice"] = "needs_context"
        elif self.mode == "refusal":
            answer = {"type": "refusal", "name": "food"}
        return httpx2.Response(200, json=decisions_response(answer))

    def mealie(self, request):
        assert request.url.host == "mealie.test", "No OFF or LLM fallback is allowed here"
        if request.url.path == "/api/organizers/tags":
            name = json.loads(request.content)["name"]
            return httpx.Response(
                200,
                json={
                    "id": name,
                    "name": name,
                    "slug": name.lower().replace(":", "-"),
                },
            )
        if request.method == "PATCH":
            patch = json.loads(request.content)
            self.patches.append(copy.deepcopy(patch))
            self.recipe.update(patch)
        return httpx.Response(200, json=self.recipe)

    @asynccontextmanager
    async def start(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(self.mealie)) as external:
            app = create_app(self.settings, http=external)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="https://app.test",
                ) as client:
                    yield app, client
            assert external.is_closed is False

    async def submit(self, app, client, trigger="estimate", expected_status="processed"):
        if trigger == "estimate":
            response = await client.post("/estimate", json={"content": {"slug": "arroz"}})
        else:
            response = await client.post(
                "/webhook",
                json={
                    "document_data": {"documentType": "recipe", "recipeSlug": "arroz"},
                },
            )
        assert response.status_code == 202
        while app.state.tasks.pending:
            await asyncio.wait_for(asyncio.gather(*list(app.state.tasks.pending)), timeout=5)
        history = (await client.get("/estimator/history.json")).json()
        assert history[0]["status"] == expected_status, history[0]
        return history[0]


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    return CatalogWorkflow(tmp_path, monkeypatch)


async def test_http_decisions_uses_catalog_nutrients_and_closes_sdk(workflow):
    original_catalog = hashlib.sha256(workflow.catalog_path.read_bytes()).digest()
    async with workflow.start() as (app, client):
        record = await workflow.submit(app, client)
        assert record["estimate"]["matchedCount"] == 1
        assert workflow.recipe["nutrition"]["calories"] == "100"
        assert workflow.recipe["nutrition"]["proteinContent"] == "5"
        trace = json.loads(workflow.recipe["extras"]["calorie_estimator_catalog"])[0]
        assert trace["id"] == "bedca:1"
        assert trace["method"] == "decisions"
        question = workflow.requests[0]["questions"][0]
        assert {item["value"] for item in question["choices"]} == {
            "bedca:1",
            "bedca:2",
            "needs_context",
        }
        context = json.loads(workflow.requests[0]["input"])
        assert context["instructions"] == workflow.recipe["recipeInstructions"][0]["text"]
        assert len(workflow.requests) == 1
    assert all(transport.is_closed for transport in workflow.sdk_transports)
    assert hashlib.sha256(workflow.catalog_path.read_bytes()).digest() == original_catalog
    with closing(sqlite3.connect(workflow.cache_path)) as db:
        tables = {
            name for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "catalog_resolution_cache" in tables
        assert not {"foods", "products", "price_observations"} & tables


@pytest.mark.parametrize("mode", ["needs_context", "refusal", "401", "429", "timeout"])
async def test_http_decisions_failures_abstain_without_retry_or_stale_calories(workflow, mode):
    workflow.mode = mode
    async with workflow.start() as (app, client):
        record = await workflow.submit(app, client)
        assert record["estimate"]["unmatchedCount"] == 1
        assert record["estimate"]["matchedCount"] == 0
        assert workflow.recipe["nutrition"]["calories"] is None
        assert workflow.recipe["extras"]["calorie_estimator_total_kcal"] == ""
        trace = json.loads(workflow.recipe["extras"]["calorie_estimator_catalog"])[0]
        assert trace["status"] == "ambiguous"
        assert len(workflow.requests) == 1


async def test_http_estimate_recovers_after_authentication_failure(workflow):
    async with workflow.start() as (app, client):
        workflow.mode = "401"
        await workflow.submit(app, client)
        workflow.mode = "success"
        await workflow.submit(app, client)
        assert workflow.recipe["nutrition"]["calories"] == "100"
        assert len(workflow.requests) == 2


async def test_sqlite_selection_survives_restart_but_note_change_invalidates_it(workflow):
    async with workflow.start() as (app, client):
        await workflow.submit(app, client)
        old_hash = workflow.recipe["extras"]["calorie_estimator_hash"]
    async with workflow.start() as (app, client):
        await workflow.submit(app, client)
        assert len(workflow.requests) == 1
        workflow.recipe["recipeIngredient"][0]["note"] = "para el acompañamiento"
        await workflow.submit(app, client, trigger="webhook")
        assert len(workflow.requests) == 2
        assert json.loads(workflow.requests[-1]["input"])["note"] == "para el acompañamiento"
        assert workflow.recipe["extras"]["calorie_estimator_hash"] != old_hash
    assert all(transport.is_closed for transport in workflow.sdk_transports)


async def test_new_catalog_version_recalculates_saved_recipe_on_webhook(workflow):
    async with workflow.start() as (app, client):
        await workflow.submit(app, client)
        old_hash = workflow.recipe["extras"]["calorie_estimator_hash"]
    with (workflow.source / "bedca_foodvalues.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        values = list(csv.DictReader(stream))
    values[0]["best_location"] = "836.8"
    make_export(workflow.source, values=values)
    import_bedca(workflow.source, workflow.catalog_path, "synthetic-v2", replace=True)
    async with workflow.start() as (app, client):
        await workflow.submit(app, client, trigger="webhook")
        assert workflow.recipe["nutrition"]["calories"] == "200"
        assert workflow.recipe["extras"]["calorie_estimator_hash"] != old_hash
        assert len(workflow.requests) == 2


async def test_failed_startup_releases_catalog_for_next_import(workflow):
    workflow.settings.decisions.api_key = ""
    with pytest.raises(ValueError, match="API key"):
        async with workflow.start():
            pytest.fail("A missing Decisions key must prevent startup")
    # A leaked read-only connection would reject a read-write connection to this same file.
    with duckdb.connect(str(workflow.catalog_path)) as db:
        assert db.execute("SELECT COUNT(*) FROM foods").fetchone()[0] == 2
    import_bedca(workflow.source, workflow.catalog_path, "synthetic-recovered", replace=True)


async def test_food_absent_from_catalog_preserves_off_fallback(workflow):
    workflow.settings.off.search_base_url = "https://off.test"
    workflow.recipe["recipeIngredient"][0]["food"]["name"] = "Alimento sin ficha"
    mealie_handler = workflow.mealie
    off_requests = []

    def external(request):
        if request.url.host == "off.test":
            off_requests.append(request)
            assert request.url.path == "/search"
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "product_name": "Synthetic OFF product",
                            "nutriments": {"energy-kcal_100g": 250, "proteins_100g": 10},
                        }
                    ]
                },
            )
        return mealie_handler(request)

    workflow.mealie = external
    async with workflow.start() as (app, client):
        record = await workflow.submit(app, client)
        assert record["estimate"]["matchedCount"] == 1
        assert workflow.recipe["nutrition"]["calories"] == "250"
        assert len(off_requests) == 1
        assert workflow.requests == []
        trace = json.loads(workflow.recipe["extras"]["calorie_estimator_catalog"])[0]
        assert trace["status"] == "not_found"


@pytest.mark.parametrize("unit", ["ml", "unidad"])
async def test_unknown_catalog_mass_never_uses_volume_or_piece_as_grams(workflow, unit):
    workflow.recipe["recipeIngredient"][0]["unit"]["name"] = unit
    async with workflow.start() as (app, client):
        record = await workflow.submit(app, client)
        assert record["estimate"]["unmatchedCount"] == 1
        assert record["estimate"]["matchedCount"] == 0
        assert workflow.recipe["nutrition"]["calories"] is None
        assert len(workflow.requests) == 1


async def test_webhook_preserves_manual_calories_without_calling_decisions(workflow):
    workflow.recipe["extras"] = {}
    workflow.recipe["nutrition"] = {"calories": "500"}
    async with workflow.start() as (app, client):
        await workflow.submit(app, client, trigger="webhook", expected_status="manual")
        assert workflow.recipe["nutrition"]["calories"] == "500"
        assert workflow.requests == []
        assert len(workflow.patches) == 1
        assert "nutrition" not in workflow.patches[0]
