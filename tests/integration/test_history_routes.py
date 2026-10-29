import httpx
import respx

from mealie_enricher.app import create_app
from mealie_enricher.config import HistorySettings, load_settings
from mealie_enricher.storage.dev_seed import seed_dev_history
from mealie_enricher.storage.history import ExecutionHistory
from tests.parity.cases import load_case


async def test_html_matches_original_byte_for_byte(tmp_path):
    case = load_case("history-html")
    settings = load_settings({**case["environment"], "CACHE_DB_PATH": str(tmp_path / "cache.db")})
    with respx.mock as mock:
        mock.get(case["expected_requests"][0]["url"]).respond(
            200, json=case["external_responses"][0]["json"]
        )
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://app.test"
            ) as http:
                response = await http.get("/estimator/history")
    expected = case["expected_result"]
    assert response.status_code == expected["status"]
    assert response.headers["content-type"] == expected["content_type"]
    assert response.headers["cache-control"] == expected["cache_control"]
    assert response.text == expected["html"]


def test_dev_seed_matches_original_and_does_not_duplicate():
    case = load_case("dev-seed")
    history = ExecutionHistory(clock_ms=lambda: case["input"]["now_ms"])
    seed_dev_history(HistorySettings(), history)
    assert history.get_history() == []
    seed_dev_history(HistorySettings(seed_dev_data=True), history)
    actual = [r.model_dump(by_alias=True, exclude={"id"}) for r in history.get_history()]
    expected = [{k: v for k, v in r.items() if k != "id"} for r in case["expected_result"]]
    assert actual == expected
    seed_dev_history(HistorySettings(seed_dev_data=True), history)
    assert len(history.get_history()) == 28
    assert ExecutionHistory().get_history() == []


async def test_app_restart_discards_history_and_dev_seed_is_opt_in(tmp_path):
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "synthetic",
            "CACHE_DB_PATH": str(tmp_path / "cache.db"),
        }
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.history.record_start("webhook", "synthetic")
        assert len(app.state.history.get_history()) == 1
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert app.state.history.get_history() == []
    settings.history.seed_dev_data = True
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert len(app.state.history.get_history()) == 28
