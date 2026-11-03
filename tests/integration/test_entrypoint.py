import json
import logging
import sys
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


@pytest.mark.skipif(sys.platform != "win32", reason="Windows psycopg requires a selector loop")
def test_postgres_entrypoint_selects_a_psycopg_compatible_windows_loop(monkeypatch):
    monkeypatch.setenv("MEALIE_API_TOKEN", "synthetic")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/enricher")
    with patch("mealie_enricher.__main__.uvicorn.run") as run:
        main()
    assert (
        run.call_args.kwargs["loop"] == "mealie_enricher.runtime.event_loop:selector_loop_factory"
    )
