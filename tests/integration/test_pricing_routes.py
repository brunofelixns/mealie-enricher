import httpx

from mealie_enricher.app import create_app
from mealie_enricher.config import load_settings


async def test_pricing_controls_are_opt_in(tmp_path):
    settings = load_settings(
        {"MEALIE_API_TOKEN": "test", "CACHE_DB_PATH": str(tmp_path / "cache.db")}
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/pricing/status")
            assert response.status_code == 404


async def test_pricing_controls_require_token_and_reject_cross_origin(tmp_path):
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
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/pricing/status")).status_code == 401
            headers = {"Authorization": "Bearer pricing-admin-test-token"}
            response = await client.get("/pricing/status", headers=headers)
            assert response.status_code == 200
            assert response.json()["postal_code"] == "27004"
            assert "pricing-admin-test-token" not in response.text
            assert "access-control-allow-origin" not in response.headers
            blocked = await client.post(
                "/pricing/sync", headers={**headers, "Origin": "https://foreign.test"}
            )
            assert blocked.status_code == 403
