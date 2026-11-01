"""Real HTTP/Docker test boundary; owns only its random Compose project."""

import json
import os
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest

from tests.integration.test_bedca_import import make_export
from tests.integration.test_docker_smoke import _free_port, _wait_until

ROOT = Path(__file__).parents[2]


def synthetic_catalog(path, raw_kcal=360):
    # Deliberately synthetic values: calculations can be checked by hand.
    values = []
    for food_id, nutrients in [
        ("1", {"ENERC": raw_kcal, "PROT": 8, "CHO": 80, "FAT": 1, "FIBT": 2}),
        ("2", {"ENERC": 120, "PROT": 3, "CHO": 26, "FAT": 0.3}),
    ]:
        for code, value in nutrients.items():
            values.append(
                {
                    "f_id": food_id,
                    "eur_name": code,
                    "best_location": str(value),
                    "v_unit": "kcal" if code == "ENERC" else "g",
                    "mu_id": "W",
                    "moex": "W",
                }
            )
    return make_export(path, values=values)


class MealieStack:
    def __init__(self, path):
        self.path = path
        self.project = "enricher-real-" + uuid.uuid4().hex[:10]
        self.source = synthetic_catalog(path / "bedca")
        self.slugs = []
        self.foods, self.units = {}, {}
        self.values = {
            "TEST_MEALIE_PORT": str(_free_port()),
            "TEST_ESTIMATOR_PORT": str(_free_port()),
            "TEST_ENV_FILE": (path / "test.env").as_posix(),
            "MEALIE_API_TOKEN": "synthetic-not-issued-yet",
            "LLM_ENABLED": "false",
            "DECISIONS_ENABLED": "false",
            "CATALOG_ENABLED": "true",
            "EVENT_DEBOUNCE_MS": "0",
            "DEV_SEED_HISTORY": "false",
            "ESTIMATE_STRATEGY": "all",
            "OFF_BASE_URL": "http://mock-off:3000",
            "BEDCA_INPUT_DIR": self.source.as_posix(),
            "BEDCA_DATASET_VERSION": "synthetic-real-mealie-v1",
        }
        self.environment = {
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
        image = os.getenv("CATALOG_TEST_IMAGE", "mealie-enricher:catalog-1.13.0")
        override = path / "isolation.json"
        override.write_text(
            json.dumps(
                {
                    "services": {
                        "calorie-estimator-test": {"image": image},
                        "catalog-import": {"image": image},
                    },
                    # Compose creates a separate network for this random project.
                    # Keep Docker Desktop's host-port forwarding available on Windows.
                }
            ),
            encoding="utf-8",
        )
        self.compose = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--env-file",
            str(path / "test.env"),
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(override),
            "--profile",
            "test",
        ]
        self.mealie = httpx.Client(
            base_url=f"http://127.0.0.1:{self.values['TEST_MEALIE_PORT']}",
            trust_env=False,
            timeout=15,
        )
        self.app = httpx.Client(
            base_url=f"http://127.0.0.1:{self.values['TEST_ESTIMATOR_PORT']}",
            trust_env=False,
            timeout=15,
        )

    def save_env(self):
        (self.path / "test.env").write_text(
            "\n".join(f"{key}={value}" for key, value in self.values.items()), encoding="utf-8"
        )

    def run(self, *args, check=True):
        result = subprocess.run(
            [*self.compose, *args],
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if check and result.returncode:
            pytest.fail(f"Isolated Compose failed: {args}\n{result.stdout}\n{result.stderr}")
        return result

    def start(self):
        self.save_env()
        self.run("up", "-d", "--pull", "never", "--wait", "mealie", "mock-off")
        password = "Synthetic-real-mealie-42!"
        response = self.mealie.post(
            "/api/users/register",
            json={
                "username": "real-e2e",
                "fullName": "Real E2E",
                "email": "real-e2e@example.test",
                "password": password,
                "passwordConfirm": password,
                "seedData": False,
                "group": "Real E2E",
            },
        )
        assert response.status_code == 201, response.text
        login = self.mealie.post(
            "/api/auth/token", data={"username": "real-e2e@example.test", "password": password}
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        self.mealie.headers["Authorization"] = "Bearer " + token
        self.values["MEALIE_API_TOKEN"] = token
        self.save_env()
        self.import_catalog()
        self.restart_app()

    def import_catalog(self, replace=False, check=True):
        args = [
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "catalog-import",
            "import-bedca",
            "--input-dir",
            "/input",
            "--output",
            "/app/catalogs/catalogos.duckdb",
            "--dataset-version",
            self.values["BEDCA_DATASET_VERSION"],
        ]
        if replace:
            args.append("--replace")
        return self.run(*args, check=check)

    def restart_app(self):
        self.run(
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--no-deps",
            "--force-recreate",
            "calorie-estimator-test",
        )
        _wait_until(lambda: self.app.get("/health").status_code == 200)

    def entity(self, kind, name):
        cache = self.foods if kind == "foods" else self.units
        if name not in cache:
            body = {"name": name}
            if kind == "units":
                body["abbreviation"] = name
            response = self.mealie.post("/api/" + kind, json=body)
            response.raise_for_status()
            cache[name] = response.json()
        return cache[name]

    def ingredient(self, name="Arroz", note="en crudo", quantity=200, unit="g"):
        return {
            "quantity": quantity,
            "unit": self.entity("units", unit),
            "food": self.entity("foods", name),
            "note": note,
            "isFood": True,
            "disableAmount": False,
        }

    def recipe(self, ingredients=None, servings=2, **fields):
        name = "Prueba aislada " + uuid.uuid4().hex[:10]
        response = self.mealie.post("/api/recipes", json={"name": name})
        assert response.status_code == 201, response.text
        slug = response.json()
        self.slugs.append(slug)
        self.patch(
            slug,
            recipeServings=servings,
            recipeYieldQuantity=servings,
            recipeIngredient=ingredients if ingredients is not None else [self.ingredient()],
            **fields,
        )
        return slug

    def patch(self, slug, **fields):
        response = self.mealie.patch("/api/recipes/" + slug, json=fields)
        response.raise_for_status()
        return response.json()

    def get(self, slug):
        response = self.mealie.get("/api/recipes/" + slug)
        response.raise_for_status()
        return response.json()

    def history(self):
        response = self.app.get("/estimator/history.json")
        response.raise_for_status()
        return response.json()

    def submit(self, slug, trigger="estimate"):
        before = {record["id"] for record in self.history()}
        payload = (
            {"document_data": {"documentType": "recipe", "recipeSlug": slug}}
            if trigger == "webhook"
            else {"content": {"slug": slug}}
        )
        response = self.app.post("/" + trigger, json=payload)
        assert response.status_code == 202, response.text

        def completed():
            records = [
                record
                for record in self.history()
                if record["id"] not in before
                and record["slug"] == slug
                and record["trigger"] == trigger
                and record["status"] != "running"
            ]
            return records[0] if records else None

        return _wait_until(completed)

    def cache_rows(self):
        script = (
            "import json,sqlite3; "
            "db=sqlite3.connect('file:/app/data/cache.db?mode=ro',uri=True); "
            "print(json.dumps(db.execute('SELECT lookup_key,resolution,updated_at "
            "FROM catalog_resolution_cache ORDER BY lookup_key').fetchall()))"
        )
        result = self.run("exec", "-T", "calorie-estimator-test", "python", "-c", script)
        return json.loads(result.stdout)

    def catalog_info(self):
        result = self.run(
            "exec",
            "-T",
            "calorie-estimator-test",
            "mealie-catalog",
            "inspect",
            "--catalog",
            "/app/catalogs/catalogos.duckdb",
        )
        return json.loads(result.stdout)

    def clear_recipes(self):
        for slug in list(self.slugs):
            response = self.mealie.delete("/api/recipes/" + slug)
            assert response.is_success or response.status_code == 404, response.text
            self.slugs.remove(slug)

    def close(self):
        self.app.close()
        self.mealie.close()
        # The random project is the whole cleanup boundary. Never prune globally.
        result = self.run("down", "--volumes", "--remove-orphans", check=False)
        assert result.returncode == 0, result.stderr
