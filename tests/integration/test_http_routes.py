import httpx
import pytest
import respx

from mealie_enricher.app import create_app
from mealie_enricher.config import load_settings
from tests.parity.cases import cases_for

CASES = [case for case in cases_for("http") if case["id"] != "history-html"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
async def test_http_contract_matches_fastify(case, tmp_path):
    settings = load_settings({**case["environment"], "CACHE_DB_PATH": str(tmp_path / "cache.db")})
    with respx.mock:
        app = create_app(settings, clock_ms=lambda: 1700000003500)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://app.test",
            ) as client:
                data = case["input"]
                kwargs = {"headers": data.get("headers", {})}
                if "payload" in data:
                    kwargs["content" if data.get("raw") else "json"] = data["payload"]
                response = await client.request(data["method"], data["url"], **kwargs)
    try:
        body = response.json()
    except ValueError:
        body = response.text
    assert {
        "status": response.status_code,
        "body": body,
        "content_type": response.headers.get("content-type"),
        "allow_origin": response.headers.get("access-control-allow-origin"),
    } == case["expected_result"]
