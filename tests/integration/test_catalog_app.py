import asyncio
import copy
import json

import httpx
import pytest

from mealie_enricher.app import create_app
from mealie_enricher.catalog.bedca import import_bedca
from mealie_enricher.config import load_settings
from tests.integration.test_bedca_import import make_export


async def test_catalog_http_processing_respects_notes_and_retains_manual_protection(tmp_path):
    source = make_export(tmp_path / "input")
    path = tmp_path / "catalog.duckdb"
    import_bedca(source, path, "synthetic-v1")
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "test",
            "MEALIE_URL": "http://mealie.test",
            "CACHE_DB_PATH": str(tmp_path / "cache.db"),
            "CATALOG_ENABLED": "true",
            "CATALOG_DB_PATH": str(path),
            "EVENT_DEBOUNCE_MS": "1",
        }
    )
    recipe = {
        "slug": "arroz",
        "name": "Arroz",
        "recipeServings": 2,
        "recipeIngredient": [
            {
                "quantity": 200,
                "unit": {"name": "g"},
                "food": {"name": "Arroz"},
                "note": "en crudo",
            }
        ],
    }
    patches = []

    def respond(request):
        assert request.url.host == "mealie.test", "El catálogo debe evitar OFF y LLM"
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
            patches.append(copy.deepcopy(patch))
            recipe.update(patch)
        return httpx.Response(200, json=recipe)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as external:
        app = create_app(settings, http=external)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://app.test",
            ) as client:
                response = await client.post("/estimate", json={"content": {"slug": "arroz"}})
                assert response.status_code == 202
                while app.state.tasks.pending:
                    await asyncio.gather(*list(app.state.tasks.pending))
                assert patches[-1]["nutrition"]["calories"] == "100"
                trace = json.loads(patches[-1]["extras"]["calorie_estimator_catalog"])
                assert trace[0]["id"] == "bedca:1"
                await app.state.processing.process_webhook("arroz")
                assert len(patches) == 1
                assert app.state.history.get_history()[-1].status in {"processed", "skipped"}

                # An ambiguous quantity must no longer retain the old raw estimate.
                recipe["recipeIngredient"][0]["note"] = ""
                await app.state.processing.process_webhook("arroz")
                record = app.state.history.get_history()[0]
                assert record.estimate.unmatched_count == 1
                trace = json.loads(patches[-1]["extras"]["calorie_estimator_catalog"])
                assert trace[0]["status"] == "ambiguous"
                assert patches[-1]["nutrition"]["calories"] is None

                # Manual protection remains effective in catalog mode too.
                recipe["extras"] = {}
                recipe["nutrition"] = {"calories": "500"}
                await app.state.processing.process_webhook("arroz")
                assert "nutrition" not in patches[-1]
                assert recipe["nutrition"]["calories"] == "500"
        assert external.is_closed is False


async def test_enabled_catalog_missing_file_rejects_startup_instead_of_using_off(tmp_path):
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "test",
            "CACHE_DB_PATH": str(tmp_path / "cache.db"),
            "CATALOG_ENABLED": "true",
            "CATALOG_DB_PATH": str(tmp_path / "missing.duckdb"),
        }
    )
    app = create_app(settings)
    with pytest.raises(ValueError, match="catálogo"):
        async with app.router.lifespan_context(app):
            pytest.fail("El servicio no debe arrancar con un catálogo inexistente")
