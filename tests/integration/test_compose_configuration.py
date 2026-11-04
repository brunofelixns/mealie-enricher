"""Validate operator examples through Compose and the real settings loader."""

import json
import os
import shutil
import subprocess
from pathlib import Path, PurePosixPath

import pytest

from mealie_enricher.config import load_settings

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = [
    ("docker-compose.yml", ".env.example"),
    ("docker/docker-compose.yml", "docker/.env.example"),
    ("docker/docker-compose.yml", "docker/.env.bedca.example"),
]


def render_compose(tmp_path, compose_path, example_path, overrides=None):
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required to validate deployment examples")
    shutil.copyfile(ROOT / compose_path, tmp_path / "compose.yml")
    text = (ROOT / example_path).read_text(encoding="utf-8")
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            (
                "MEALIE_",
                "OFF_",
                "LLM_",
                "DECISIONS_",
                "OPENAI_",
                "NOVA_",
                "PRICING_",
                "MERCADONA_",
                "POSTGRES_",
                "PG",
                "DATABASE_",
                "CATALOG_",
                "BEDCA_",
                "HISTORY_",
                "ESTIMATE_",
                "EVENT_",
                "DEV_SEED_",
                "TEST_",
            )
        )
        and key not in {"PORT", "PUBLISHED_PORT", "LOG_LEVEL", "CACHE_DB_PATH"}
    }
    environment.update(overrides or {})
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "enricher-config-check",
            "--project-directory",
            str(tmp_path),
            "--file",
            str(tmp_path / "compose.yml"),
            "--env-file",
            str(tmp_path / ".env"),
            "config",
            "--format",
            "json",
        ],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(("compose_path", "example_path"), EXAMPLES)
def test_examples_use_bundled_bedca_and_persistent_runtime_data(
    tmp_path, compose_path, example_path
):
    config = render_compose(tmp_path, compose_path, example_path)
    services = config["services"]
    application = services["calorie-estimator"]
    settings = load_settings({**application["environment"], "MEALIE_API_TOKEN": "synthetic"})
    assert settings.catalog.enabled
    assert settings.catalog.db_path == "/opt/bedca/catalogos.duckdb"
    assert not settings.llm.enabled
    assert not settings.nova_enabled
    assert not settings.pricing.enabled
    assert settings.pricing.postal_code == "27004"
    assert settings.pricing.sync_interval_hours == 168
    assert settings.database_url == "postgresql+psycopg://postgres:5432/mealie_enricher"
    assert services["postgres"]["environment"]["POSTGRES_PASSWORD"]
    assert not services["postgres"].get("ports")
    assert any(volume["target"] == "/app/data" for volume in application["volumes"])
    for path in (settings.cache.db_path, settings.pricing.data_dir):
        assert PurePosixPath("/app", path).is_relative_to("/app/data")


@pytest.mark.parametrize(("compose_path", "example_path"), EXAMPLES)
def test_both_compose_files_forward_optional_enrichment_overrides(
    tmp_path, compose_path, example_path
):
    config = render_compose(
        tmp_path,
        compose_path,
        example_path,
        {
            "NOVA_ENABLED": "true",
            "OPENAI_API_KEY": "synthetic-openai",
            "DECISIONS_API_KEY": "synthetic-decisions",
            "DECISIONS_MODEL": "synthetic-model",
            "DECISIONS_MIN_CONFIDENCE": "0.95",
            "DECISIONS_TIMEOUT_SECONDS": "35",
            "DECISIONS_MAX_CONCURRENCY": "3",
            "PRICING_ENABLED": "true",
            "PRICING_ADMIN_TOKEN": "synthetic-pricing-admin-token",
            "MERCADONA_POSTAL_CODE": "28001",
            "PRICING_SYNC_INTERVAL_HOURS": "24",
            "PRICING_AUTO_SYNC": "false",
            "PRICING_REQUEST_DELAY_SECONDS": "0.5",
            "PRICING_MAX_PRODUCTS": "8000",
            "PRICING_MAX_CANDIDATES": "10",
            "PRICING_MAX_DECISIONS_PER_RUN": "50",
            "HISTORY_RETENTION_DAYS": "90",
            "MEALIE_TIMEOUT_MS": "45000",
            "OFF_MAX_RETRIES": "4",
            "OFF_RETRY_BACKOFF_MS": "750",
            "MEALIE_RECIPE_URL_TEMPLATE": "https://recipes.example.test/recipe/{slug}",
        },
    )
    settings = load_settings(
        {**config["services"]["calorie-estimator"]["environment"], "MEALIE_API_TOKEN": "synthetic"}
    )
    assert settings.nova_enabled
    assert settings.decisions.api_key == "synthetic-decisions"
    assert settings.decisions.model == "synthetic-model"
    assert settings.decisions.min_confidence == 0.95
    assert settings.decisions.timeout_seconds == 35
    assert settings.decisions.max_concurrency == 3
    assert settings.pricing.enabled
    assert settings.pricing.postal_code == "28001"
    assert settings.pricing.sync_interval_hours == 24
    assert not settings.pricing.auto_sync
    assert settings.pricing.request_delay_seconds == 0.5
    assert settings.pricing.max_products == 8000
    assert settings.pricing.max_candidates == 10
    assert settings.pricing.max_decisions_per_run == 50
    assert settings.history.retention_days == 90
    assert settings.mealie.timeout_ms == 45000
    assert settings.off.max_retries == 4
    assert settings.off.retry_backoff_ms == 750
    assert settings.history.recipe_url_template == "https://recipes.example.test/recipe/{slug}"


@pytest.mark.parametrize(("compose_path", "example_path"), EXAMPLES)
def test_environment_files_keep_household_tokens_and_literal_dollars(
    tmp_path, compose_path, example_path
):
    copied = tmp_path / ".env.example"
    copied.write_text(
        (ROOT / example_path).read_text(encoding="utf-8")
        + "\nMEALIE_API_TOKEN_EXTRA_HOME='synthetic$household'\n",
        encoding="utf-8",
    )
    # render_compose accepts absolute example paths as well as repository paths.
    config = render_compose(tmp_path, compose_path, str(copied))
    tokens = config["services"]["calorie-estimator"]["environment"]
    # `config` doubles dollars so the resulting YAML/JSON can be reloaded safely.
    assert tokens["MEALIE_API_TOKEN_EXTRA_HOME"].replace("$$", "$") == "synthetic$household"
