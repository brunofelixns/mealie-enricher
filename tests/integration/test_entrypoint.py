import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mealie_enricher.__main__ import main
from mealie_enricher.logging import JsonFormatter


def test_entrypoint_uses_configured_port_and_one_worker(monkeypatch):
    monkeypatch.setenv("MEALIE_API_TOKEN", "synthetic-entrypoint")
    monkeypatch.setenv("PORT", "8123")
    with patch("mealie_enricher.__main__.uvicorn.run") as run:
        main()
    assert run.call_args.kwargs["host"] == "0.0.0.0"
    assert run.call_args.kwargs["port"] == 8123
    assert run.call_args.kwargs["workers"] == 1
    assert run.call_args.kwargs["log_config"] is None


def test_logging_outputs_machine_readable_events():
    record = logging.LogRecord("service", logging.INFO, "", 0, "Processed %s", ("recipe",), None)
    result = json.loads(JsonFormatter().format(record))
    assert result["level"] == "info"
    assert result["msg"] == "Processed recipe"
    assert isinstance(result["time"], int)


@pytest.mark.parametrize(
    ("platform", "database_url", "expected"),
    [
        (
            "win32",
            "postgresql://localhost/enricher",
            "mealie_enricher.runtime.event_loop:selector_loop_factory",
        ),
        ("linux", "postgresql://localhost/enricher", "auto"),
        ("win32", "", "auto"),
        ("linux", "", "auto"),
    ],
)
def test_entrypoint_uses_selector_only_for_windows_postgres(
    monkeypatch, platform, database_url, expected
):
    monkeypatch.setattr("mealie_enricher.__main__.sys", SimpleNamespace(platform=platform))
    monkeypatch.setenv("MEALIE_API_TOKEN", "synthetic")
    monkeypatch.setenv("DATABASE_URL", database_url)
    with patch("mealie_enricher.__main__.uvicorn.run") as run:
        main()
    assert run.call_args.kwargs["loop"] == expected
