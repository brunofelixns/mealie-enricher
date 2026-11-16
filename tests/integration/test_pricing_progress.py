import asyncio
import json

import httpx
import pytest

from mealie_enricher.app import create_app
from mealie_enricher.config import load_settings
from mealie_enricher.pricing.mercadona import MercadonaClient
from tests.integration.test_pricing_catalog import MercadonaAPI


async def test_download_reports_completed_products_before_download_finishes():
    api = MercadonaAPI()
    events = []
    reached, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        if request.url.path == "/api/products/101/":
            reached.set()
            await release.wait()
        return api(request)

    def report(stage, completed, total, current):
        events.append((stage, completed, total, current))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        source = MercadonaClient(http, delay_seconds=0, on_progress=report)
        task = asyncio.create_task(source.download("27004"))
        try:
            await asyncio.wait_for(reached.wait(), 2)
            assert not task.done()
            assert ("products", 1, 2, "100") in events
            release.set()
            result = await task
            assert len(result.products) == 2
            assert events[-1] == ("products", 2, 2, "101")
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


def test_progress_checkpoints_keep_real_counts_and_unknown_totals(tmp_path, caplog):
    from mealie_enricher.pricing.progress import PricingProgress
    from mealie_enricher.pricing.state import PricingState

    state = PricingState(str(tmp_path))
    progress = PricingProgress(state)
    progress.begin("selecting_postal_code")
    assert progress.snapshot()["percent"] is None
    with caplog.at_level("INFO"):
        progress.update("products", 1, 2, "100")
    assert progress.snapshot()["percent"] == 50.0
    assert "1/2" in caplog.text
    saved = json.loads(state.path.read_text())
    assert saved["progress"]["completed"] == 1
    assert saved["progress"]["total"] == 2
    progress.update("products", 2, 2, "101")
    assert progress.snapshot()["eta_seconds"] == 0
    assert progress.snapshot()["downloaded_products"] == 2
    assert progress.snapshot()["last_activity_at"] is not None


@pytest.mark.parametrize("origin", [None, "http://test", "https://foreign.test", "null"])
async def test_progress_endpoint_requires_bearer_and_allows_only_same_origin(tmp_path, origin):
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "test",
            "OPENAI_API_KEY": "test-key",
            "CACHE_DB_PATH": str(tmp_path / "cache.db"),
            "PRICING_ENABLED": "true",
            "PRICING_AUTO_SYNC": "false",
            "PRICING_ADMIN_TOKEN": "pricing-admin-test-token",
            "PRICING_DATA_DIR": str(tmp_path / "pricing"),
        }
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.pricing.progress.begin("products")
        app.state.pricing.progress.update("products", 1, 2, "100")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/pricing/progress")).status_code == 401
            headers = {"Authorization": "Bearer pricing-admin-test-token"}
            if origin is not None:
                headers["Origin"] = origin
            response = await client.get("/pricing/progress", headers=headers)
            assert response.status_code == (200 if origin in (None, "http://test") else 403)
            if response.status_code == 200:
                assert response.json()["completed"] == 1
                assert response.json()["percent"] == 50.0
                assert "pricing-admin-test-token" not in response.text
                assert "test-key" not in response.text
            assert "access-control-allow-origin" not in response.headers


def test_restart_preserves_last_progress_and_marks_interrupted_job(tmp_path):
    from mealie_enricher.pricing.progress import PricingProgress
    from mealie_enricher.pricing.state import PricingState

    state = PricingState(str(tmp_path))
    state.data.update(running=True, phase="downloading")
    progress = PricingProgress(state)
    progress.begin("products")
    progress.update("products", 1, 2, "100")
    restarted = PricingState(str(tmp_path))
    recovered = PricingProgress(restarted).snapshot()
    assert restarted.data["phase"] == "interrupted"
    assert not restarted.data["running"]
    assert recovered["completed"] == 1
    assert recovered["percent"] == 50.0
    assert recovered["finished_at"] is not None
    assert recovered["eta_seconds"] is None
    restarted.data["progress"]["finished_at"] = 1234.0
    assert PricingProgress(restarted).snapshot()["finished_at"] == 1234.0


async def test_sync_failure_exposes_useful_error_without_tokens_or_losing_catalog(tmp_path):
    from mealie_enricher.pricing.service import PricingService
    from mealie_enricher.runtime.slug_queue import SlugQueue
    from tests.integration.test_pricing_service import Mealie, Selector, settings, snapshot

    config = settings(tmp_path)
    async with httpx.AsyncClient() as http:
        service = PricingService(config, http, Mealie(), SlugQueue(), selector=Selector())
        try:
            service.store.publish(snapshot())

            async def failed(postal_code):
                raise ValueError("Mercadona HTTP 403 " + config.pricing.admin_token)

            service.source.download = failed
            await service.sync()
            result = service.status()
            assert result["phase"] == "error"
            assert result["last_error"] == "ValueError"
            assert "HTTP 403" in result["last_error_detail"]
            assert config.pricing.admin_token not in json.dumps(result)
            assert result["progress"]["finished_at"] is not None
            assert service.store.load("mercadona", "27004") is not None
        finally:
            await service.close()
