"""Exercise the shipped deployment Compose with a real application and PostgreSQL."""

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SMOKE") != "1", reason="Set RUN_DOCKER_SMOKE=1 for isolated Docker E2E"
)


def test_deployment_compose_retains_history_after_both_containers_are_recreated(tmp_path):
    root = Path(__file__).resolve().parents[2]
    shutil.copyfile(root / "docker/docker-compose.yml", tmp_path / "docker-compose.yml")
    image = os.getenv(
        "POSTGRES_COMPOSE_TEST_IMAGE", os.getenv("CATALOG_TEST_IMAGE", "mealie-enricher:local")
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MEALIE_ENRICHER_IMAGE=" + image,
                "PUBLISHED_PORT=0",
                "MEALIE_URL=http://127.0.0.1:9",
                "MEALIE_API_TOKEN=synthetic-postgres-compose",
                "MEALIE_TIMEOUT_MS=1000",
                "POSTGRES_PASSWORD='test@:/%#$password'",
                "CATALOG_ENABLED=false",
            ]
        ),
        encoding="utf-8",
    )
    project = "enricher-pg-test-" + uuid.uuid4().hex[:12]

    def compose(*args, check=True):
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--project-name",
                project,
                "--file",
                str(tmp_path / "docker-compose.yml"),
                "--project-directory",
                str(tmp_path),
                *args,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
            check=False,
            env={
                key: value
                for key, value in os.environ.items()
                if key
                not in {
                    "DATABASE_URL",
                    "POSTGRES_PASSWORD",
                    "POSTGRES_DB",
                    "POSTGRES_USER",
                    "MEALIE_ENRICHER_IMAGE",
                    "PUBLISHED_PORT",
                    "PORT",
                }
            },
        )
        if check and result.returncode:
            pytest.fail(f"Isolated Compose failed: {args}\n{result.stdout}\n{result.stderr}")
        return result

    def url():
        published = compose("port", "calorie-estimator", "8000").stdout.splitlines()[0]
        return "http://127.0.0.1:" + published.rsplit(":", 1)[1]

    try:
        config = json.loads(compose("config", "--format", "json").stdout)
        assert not config["services"]["postgres"].get("ports")
        compose("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "90")
        # `compose config` escapes dollars for round-tripping; inspect the actual
        # container environment to verify the password is passed unchanged.
        actual_password = compose(
            "exec",
            "-T",
            "calorie-estimator",
            "python",
            "-c",
            "import json,os; print(json.dumps(os.environ['PGPASSWORD']))",
        ).stdout
        assert json.loads(actual_password) == "test@:/%#$password"
        with httpx.Client(base_url=url(), timeout=5, trust_env=False) as client:
            response = client.post("/estimate", json={"content": {"slug": "persistent-example"}})
            assert response.status_code == 202
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                records = client.get("/estimator/history.json").json()
                if records and records[0]["status"] == "error":
                    break
                time.sleep(0.2)
            else:
                pytest.fail("The isolated recipe request did not finish")
            original = records
        compose(
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "90",
        )
        with httpx.Client(base_url=url(), timeout=5, trust_env=False) as client:
            assert client.get("/estimator/history.json").json() == original
    finally:
        # Only this test's unique Compose project and its disposable volumes.
        compose("down", "--volumes", "--remove-orphans", check=False)
