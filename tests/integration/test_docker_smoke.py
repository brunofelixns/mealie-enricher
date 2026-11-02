"""Opt-in real Mealie integration. Creates and removes only its own Compose project."""

import json
import os
import socket
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SMOKE") != "1", reason="Set RUN_DOCKER_SMOKE=1 for isolated Docker E2E"
)
ROOT = Path(__file__).parents[2]


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until(check, seconds=60):
    deadline = time.monotonic() + seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (httpx.HTTPError, AssertionError) as error:
            last_error = error
        time.sleep(0.25)
    raise AssertionError(f"Readiness timed out: {last_error}")


def test_container_with_real_mealie_and_synthetic_off(tmp_path):
    project = "enricher-smoke-" + uuid.uuid4().hex[:10]
    mealie_port, estimator_port = _free_port(), _free_port()
    env_path = tmp_path / "smoke.env"
    values = {
        "TEST_MEALIE_PORT": str(mealie_port),
        "TEST_ESTIMATOR_PORT": str(estimator_port),
        "TEST_ENV_FILE": str(env_path).replace("\\", "/"),
        "MEALIE_API_TOKEN": "not-issued-yet",
        "LLM_ENABLED": "false",
        "LLM_API_KEY": "",
        "EVENT_DEBOUNCE_MS": "0",
        "OFF_LANGUAGE": "de",
        "DEV_SEED_HISTORY": "false",
    }

    if image_override := os.environ.get("TEST_MEALIE_IMAGE"):
        values["TEST_MEALIE_IMAGE"] = image_override

    def save_env():
        env_path.write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")

    save_env()
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            (
                "MEALIE_",
                "OFF_",
                "LLM_",
                "EVENT_",
                "HISTORY_",
                "DEV_SEED_",
                "ESTIMATE_",
                "TEST_",
                "OPENAI_",
                "DECISIONS_",
                "CATALOG_",
                "BEDCA_",
            )
        )
    }
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(env_path),
        "-f",
        str(ROOT / "docker-compose.yml"),
        "--profile",
        "test",
    ]

    def run(*args, check=True, timeout=240):
        result = subprocess.run(
            [*compose, *args],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if check and result.returncode:
            pytest.fail(f"Compose failed: {args}\n{result.stdout}\n{result.stderr}")
        return result

    try:
        run("up", "-d", "--wait", "mealie", "mock-off")
        with httpx.Client(base_url=f"http://127.0.0.1:{mealie_port}", timeout=10) as mealie:
            password = "Synthetic-smoke-only-42!"
            response = mealie.post(
                "/api/users/register",
                json={
                    "username": "migration-smoke",
                    "fullName": "Migration Smoke",
                    "email": "migration-smoke@example.test",
                    "password": password,
                    "passwordConfirm": password,
                    "seedData": False,
                    "group": "Migration Smoke",
                },
            )
            assert response.status_code == 201, response.text
            login = mealie.post(
                "/api/auth/token",
                data={
                    "username": "migration-smoke@example.test",
                    "password": password,
                },
            )
            login.raise_for_status()
            token = login.json()["access_token"]
            mealie.headers["Authorization"] = "Bearer " + token
            values["MEALIE_API_TOKEN"] = token
            save_env()

            response = mealie.post("/api/recipes", json={"name": "Migration synthetic flour"})
            assert response.status_code == 201, response.text
            slug = response.json()
            food_response = mealie.post("/api/foods", json={"name": "mehl"})
            unit_response = mealie.post("/api/units", json={"name": "g", "abbreviation": "g"})
            food_response.raise_for_status()
            unit_response.raise_for_status()
            patch = mealie.patch(
                "/api/recipes/" + slug,
                json={
                    "recipeServings": 2,
                    "recipeYieldQuantity": 2,
                    "recipeIngredient": [
                        {
                            "quantity": 100,
                            "unit": unit_response.json(),
                            "food": food_response.json(),
                            "note": "",
                            "isFood": True,
                            "disableAmount": False,
                        }
                    ],
                    "extras": {"synthetic-marker": "keep"},
                },
            )
            assert patch.status_code == 200, patch.text
            run("up", "-d", "--no-build", "calorie-estimator-test")

            with httpx.Client(base_url=f"http://127.0.0.1:{estimator_port}", timeout=10) as app:
                _wait_until(lambda: app.get("/health").is_success)
                response = app.post("/estimate", json={"content": {"slug": slug}})
                assert response.status_code == 202, response.text

                def finished(trigger):
                    records = app.get("/estimator/history.json").json()
                    matches = [r for r in records if r["trigger"] == trigger]
                    if not matches or matches[0]["status"] == "running":
                        return None
                    return matches[0]

                estimated = _wait_until(lambda: finished("estimate"))
                assert estimated["status"] == "processed", estimated
                assert estimated["estimate"]["nutrients"]["kcalPer100g"] == 182
                recipe = mealie.get("/api/recipes/" + slug).json()
                assert recipe["nutrition"]["calories"] == "182"
                assert recipe["extras"]["synthetic-marker"] == "keep"
                assert recipe["extras"]["calorie_estimator_hash"]
                assert len(recipe["tags"]) == 2
                assert {tag["name"] for tag in recipe["tags"]} == {
                    "Calorías:Bajas",
                    "Digestión:Fácil",
                }
                response = app.post(
                    "/webhook",
                    json={
                        "document_data": {"documentType": "recipe", "recipeSlug": slug},
                    },
                )
                assert response.status_code == 202
                assert _wait_until(lambda: finished("webhook"))["status"] == "skipped"
                assert app.get("/estimator/history").status_code == 200

            # Switch this isolated project to catalog mode and validate actual Mealie NULLs.
            from tests.integration.test_bedca_import import make_export

            source = make_export(tmp_path / "bedca")
            values.update(
                {
                    "CATALOG_ENABLED": "true",
                    "DECISIONS_ENABLED": "false",
                    "BEDCA_INPUT_DIR": source.as_posix(),
                    "BEDCA_DATASET_VERSION": "synthetic-mealie-v1",
                }
            )
            save_env()
            run("run", "--rm", "catalog-import")
            run("up", "-d", "--no-build", "--no-deps", "--force-recreate", "calorie-estimator-test")
            rice = mealie.post("/api/foods", json={"name": "Arroz"})
            rice.raise_for_status()
            ingredient = {
                "quantity": 200,
                "unit": unit_response.json(),
                "food": rice.json(),
                "note": "en crudo",
                "isFood": True,
                "disableAmount": False,
            }
            changed = mealie.patch(
                "/api/recipes/" + slug,
                json={"recipeIngredient": [ingredient]},
            )
            changed.raise_for_status()
            with httpx.Client(base_url=f"http://127.0.0.1:{estimator_port}", timeout=10) as app:
                _wait_until(lambda: app.get("/health").is_success)
                response = app.post("/estimate", json={"content": {"slug": slug}})
                assert response.status_code == 202
                assert _wait_until(lambda: finished("estimate"))["status"] == "processed"
                recipe = mealie.get("/api/recipes/" + slug).json()
                assert recipe["nutrition"]["calories"] == "100"
                assert (
                    json.loads(recipe["extras"]["calorie_estimator_catalog"])[0]["id"] == "bedca:1"
                )
                ingredient["note"] = ""
                mealie.patch(
                    "/api/recipes/" + slug, json={"recipeIngredient": [ingredient]}
                ).raise_for_status()
                response = app.post(
                    "/webhook",
                    json={
                        "document_data": {"documentType": "recipe", "recipeSlug": slug},
                    },
                )
                assert response.status_code == 202
                record = _wait_until(lambda: finished("webhook"))
                assert record["status"] == "processed", record
                assert record["estimate"]["unmatchedCount"] == 1
                recipe = mealie.get("/api/recipes/" + slug).json()
                assert recipe["nutrition"]["calories"] is None

            container = run("ps", "-q", "calorie-estimator-test").stdout.strip()
            inspection = subprocess.run(
                ["docker", "inspect", container],
                capture_output=True,
                text=True,
                check=True,
            )
            assert json.loads(inspection.stdout)[0]["Config"]["User"] == "appuser"
    finally:
        # The random project name is the only deletion target; no shared/production volumes.
        result = run("down", "--volumes", "--remove-orphans", check=False)
        assert result.returncode == 0, result.stderr


def test_compose_test_env_file_keeps_mealie_token(tmp_path):
    token_file = tmp_path / "tokens.env"
    token_file.write_text("MEALIE_API_TOKEN=synthetic-from-test-env-file\n", encoding="utf-8")
    variables = tmp_path / "variables.env"
    variables.write_text(
        "TEST_ENV_FILE=" + str(token_file).replace("\\", "/") + "\n",
        encoding="utf-8",
    )
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("MEALIE_", "TEST_", "OPENAI_", "DECISIONS_", "CATALOG_", "BEDCA_"))
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(variables),
            "-f",
            str(ROOT / "docker-compose.yml"),
            "--profile",
            "test",
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    configuration = json.loads(result.stdout)
    actual = configuration["services"]["calorie-estimator-test"]["environment"]
    assert actual["MEALIE_API_TOKEN"] == "synthetic-from-test-env-file"
