import asyncio
import json

import httpx
import pytest
import respx

from mealie_enricher.app import create_app
from mealie_enricher.config import load_settings
from tests.parity.cases import cases_for
from tests.parity.spanish import spanish_labels


def normalize_ids(value):
    ids = {}

    def walk(item):
        if isinstance(item, dict):
            return {
                key: (
                    ids.setdefault(val, "00000000-0000-4000-8000-" + str(len(ids) + 1).zfill(12))
                    if key == "id" and isinstance(val, str) and len(val) == 36
                    else walk(val)
                )
                for key, val in item.items()
            }
        if isinstance(item, list):
            return [walk(val) for val in item]
        return item

    return walk(value)


@pytest.mark.parametrize("case", cases_for("processing"), ids=lambda c: c["id"])
async def test_complete_workflow_matches_original_http_writes_and_history(case, tmp_path):
    case = spanish_labels(case)
    settings = load_settings({**case["environment"], "CACHE_DB_PATH": str(tmp_path / "cache.db")})
    pending = list(zip(case["expected_requests"], case["external_responses"], strict=True))
    observed = []

    def respond(request):
        body = json.loads(request.content) if request.content else None
        record = {"method": request.method, "url": str(request.url)}
        if body is not None:
            record["json"] = body
        if request.url.host == "127.0.0.1":
            record["authorization"] = request.headers["authorization"]
        observed.append(record)
        for index, (expected, external) in enumerate(pending):
            if (
                record["method"] == expected["method"]
                and record["url"] == expected["url"]
                and record.get("json") == expected.get("json")
            ):
                pending.pop(index)
                return httpx.Response(external["status"], json=external["json"])
        raise AssertionError(f"Unexpected request: {record}")

    with respx.mock as router:
        router.route().mock(side_effect=respond)
        async with httpx.AsyncClient() as external:
            records = case["expected_result"]["history"]
            clock = records[0]["startedAt"] if records else 1700000003500
            app = create_app(settings, http=external, clock_ms=lambda: clock)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://app.test"
                ) as client:
                    trigger = case["input"]["trigger"]
                    slug = case["input"]["recipe"]["slug"]
                    payload = (
                        {"document_data": {"document_type": "recipe", "recipe_slug": slug}}
                        if trigger == "webhook"
                        else {"content": {"slug": slug}}
                    )
                    response = await client.post("/" + trigger, json=payload)
                    while app.state.tasks.pending:
                        await asyncio.gather(*list(app.state.tasks.pending))
                    actual = {
                        "status": response.status_code,
                        "body": response.json(),
                        "history": [
                            record.model_dump(by_alias=True)
                            for record in app.state.history.get_history()
                        ],
                        "patches": [
                            request["json"] for request in observed if request["method"] == "PATCH"
                        ],
                    }
    assert normalize_ids(actual) == case["expected_result"]
    assert observed == case["expected_requests"]
    assert pending == []
