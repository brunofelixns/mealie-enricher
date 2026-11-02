"""Opt-in deployment proof using only an isolated project and synthetic CSV."""

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest

from tests.integration.test_bedca_import import make_export
from tests.integration.test_docker_smoke import _free_port, _wait_until

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SMOKE") != "1", reason="Set RUN_DOCKER_SMOKE=1 for isolated Docker E2E"
)
ROOT = Path(__file__).parents[2]


def test_deployment_imports_catalog_then_opens_it_read_only(tmp_path):
    project = "enricher-catalog-" + uuid.uuid4().hex[:10]
    source = make_export(tmp_path / "bedca")
    shutil.copyfile(ROOT / "docker/docker-compose.yml", tmp_path / "docker-compose.yml")
    port = _free_port()
    values = {
        "MEALIE_ENRICHER_IMAGE": os.getenv("CATALOG_TEST_IMAGE", "mealie-enricher:local"),
        "MEALIE_API_TOKEN": "synthetic-not-used",
        "MEALIE_URL": "http://unused.invalid",
        "PUBLISHED_PORT": str(port),
        "CATALOG_ENABLED": "true",
        "DECISIONS_ENABLED": "false",
        "LLM_ENABLED": "false",
        "BEDCA_INPUT_DIR": source.as_posix(),
        "BEDCA_DATASET_VERSION": "synthetic-docker-v1",
    }
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()), encoding="utf-8"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("MEALIE_", "CATALOG_", "DECISIONS_", "OPENAI_", "BEDCA_"))
    }
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(env_file),
        "-f",
        str(tmp_path / "docker-compose.yml"),
    ]

    def run(*args, check=True):
        result = subprocess.run(
            [*compose, *args],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if check and result.returncode:
            pytest.fail(f"Compose failed: {args}\n{result.stdout}\n{result.stderr}")
        return result

    try:
        report = json.loads(run("--profile", "catalog", "run", "--rm", "catalog-import").stdout)
        assert report["food_count"] == 2
        assert report["dataset_version"] == "synthetic-docker-v1"
        run("up", "-d", "--no-build", "--pull", "never", "--wait", "calorie-estimator")
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            _wait_until(lambda: client.get("/health").status_code == 200)
            assert client.get("/estimator/history.json").json() == []
        container = run("ps", "-q", "calorie-estimator").stdout.strip()
        result = subprocess.run(
            ["docker", "inspect", container],
            capture_output=True,
            text=True,
            check=True,
        )
        info = json.loads(result.stdout)[0]
        assert info["Config"]["User"] == "appuser"
        mounts = {entry["Destination"]: entry for entry in info["Mounts"]}
        assert mounts["/app/catalogs"]["RW"] is False
        assert mounts["/app/data"]["RW"] is True
        assert mounts["/app/catalogs"]["Name"] != mounts["/app/data"]["Name"]
        search = run(
            "exec",
            "-T",
            "calorie-estimator",
            "mealie-catalog",
            "search",
            "--catalog",
            "/app/catalogs/catalogos.duckdb",
            "--name",
            "arroz",
        )
        assert {row["id"] for row in json.loads(search.stdout)} == {"bedca:1", "bedca:2"}
    finally:
        # The random project is the complete cleanup boundary; no user volumes are touched.
        result = run("down", "--volumes", "--remove-orphans", check=False)
        assert result.returncode == 0, result.stderr
