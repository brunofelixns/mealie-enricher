"""Opt-in proof that bundled BEDCA works without a deployment-time import."""

import hashlib
import json
import os
import shutil
import subprocess
import uuid

import httpx
import pytest

from tests.integration.test_docker_smoke import _free_port, _wait_until
from tests.support.mealie_stack import ROOT, MealieStack, synthetic_catalog

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SMOKE") != "1", reason="Set RUN_DOCKER_SMOKE=1 for isolated Docker E2E"
)


def docker(*args, check=True):
    result = subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
    )
    if check and result.returncode:
        pytest.fail(f"Docker failed: {args}\n{result.stdout}\n{result.stderr}")
    return result


@pytest.mark.parametrize("compose_path", ["docker-compose.yml", "docker/docker-compose.yml"])
def test_compose_accepts_bundled_catalog_path(tmp_path, compose_path):
    shutil.copyfile(ROOT / compose_path, tmp_path / "docker-compose.yml")
    (tmp_path / ".env").write_text("", encoding="utf-8")
    env_file = tmp_path / "bundle.env"
    env_file.write_text(
        "MEALIE_ENRICHER_IMAGE=synthetic:bedca\nCATALOG_DB_PATH=/opt/bedca/catalogos.duckdb\n",
        encoding="utf-8",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("MEALIE_", "CATALOG_", "OPENAI_", "DECISIONS_"))
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "config",
            "--no-env-resolution",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    assert config["services"]["calorie-estimator"]["environment"]["CATALOG_DB_PATH"] == (
        "/opt/bedca/catalogos.duckdb"
    )


@pytest.fixture(scope="module")
def bundles(tmp_path_factory):
    path = tmp_path_factory.mktemp("bedca-bundle")
    tags, sources = [], []

    def build(source, version, check=True):
        tag = "mealie-enricher:bundle-test-" + uuid.uuid4().hex[:12]
        tags.append(tag)
        result = docker(
            "buildx",
            "build",
            "--load",
            "--network",
            "none",
            "--build-context",
            "bedca_source=" + source.as_posix(),
            "--build-arg",
            "BASE_IMAGE=" + os.getenv("CATALOG_TEST_IMAGE", "mealie-enricher:local"),
            "--build-arg",
            "BEDCA_DATASET_VERSION=" + version,
            "-f",
            "docker/Dockerfile.bedca",
            "-t",
            tag,
            ".",
            check=check,
        )
        return tag, result

    try:
        for index, kcal in enumerate((360, 400), 1):
            source = synthetic_catalog(path / str(index), raw_kcal=kcal)
            # Arbitrary files in the named context must not enter the image.
            (source / ".env").write_text("SYNTHETIC_SENTINEL=exclude-me\n", encoding="utf-8")
            tag, _ = build(source, "synthetic-bundled-v" + str(index))
            sources.append((tag, source))
        yield sources, build, path
    finally:
        for tag in tags:
            # Remove only this test's unique tags, never prune shared images.
            docker("image", "rm", tag, check=False)


def test_image_preserves_csv_manifest_attribution_and_read_only_permissions(bundles):
    sources, _, _ = bundles
    tag, source = sources[0]
    script = """
import hashlib,json,os,pathlib
root=pathlib.Path('/opt/bedca')
files=list((root/'source').iterdir())
assert os.getuid()==1000
assert os.environ['CATALOG_ENABLED']=='true'
assert os.environ['CATALOG_DB_PATH']=='/opt/bedca/catalogos.duckdb'
assert not (root/'source/.env').exists()
assert all(not (p.stat().st_mode & 0o222) for p in [root/'catalogos.duckdb',*files])
assert 'AESAN/BEDCA' in (root/'NOTICE.md').read_text()
print(json.dumps({'csv':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                 'manifest':json.loads((root/'manifest.json').read_text())}))
"""
    result = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--entrypoint",
        "python",
        tag,
        "-c",
        script,
    )
    report = json.loads(result.stdout)
    expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.csv")}
    assert report["csv"] == expected
    assert report["manifest"]["food_count"] == 2
    assert report["manifest"]["dataset_version"] == "synthetic-bundled-v1"


def test_invalid_bedca_cannot_produce_a_bundle(bundles):
    _, build, path = bundles
    source = synthetic_catalog(path / "invalid", raw_kcal=-1)
    tag, result = build(source, "invalid", check=False)
    assert result.returncode != 0
    assert "negativo" in result.stderr
    assert docker("image", "inspect", tag, check=False).returncode != 0


def test_bundled_image_starts_in_deployment_compose_without_importing(bundles, tmp_path):
    sources, _, _ = bundles
    project = "enricher-bundle-deploy-" + uuid.uuid4().hex[:10]
    shutil.copyfile(ROOT / "docker/docker-compose.yml", tmp_path / "docker-compose.yml")
    env_file = tmp_path / ".env"
    values = {
        "MEALIE_ENRICHER_IMAGE": sources[0][0],
        "MEALIE_API_TOKEN": "synthetic-unused",
        "MEALIE_URL": "http://unused.invalid",
        "PUBLISHED_PORT": str(_free_port()),
        "CATALOG_ENABLED": "true",
        "CATALOG_DB_PATH": "/opt/bedca/catalogos.duckdb",
        "DECISIONS_ENABLED": "false",
        "LLM_ENABLED": "false",
    }
    env_file.write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("MEALIE_", "CATALOG_", "OPENAI_", "DECISIONS_", "BEDCA_"))
    }

    def compose(*args):
        return subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "--env-file",
                str(env_file),
                "-f",
                str(tmp_path / "docker-compose.yml"),
                *args,
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )

    try:
        compose("up", "-d", "--no-build", "--pull", "never", "--wait", "calorie-estimator")
        with httpx.Client(
            base_url="http://127.0.0.1:" + values["PUBLISHED_PORT"], trust_env=False
        ) as client:
            _wait_until(lambda: client.get("/health").is_success)
        script = (
            "from pathlib import Path; assert not Path('/app/catalogs/catalogos.duckdb').exists(); "
            "assert Path('/opt/bedca/catalogos.duckdb').is_file()"
        )
        compose("exec", "-T", "calorie-estimator", "python", "-c", script)
    finally:
        compose("down", "--volumes", "--remove-orphans")


def test_bundled_catalog_reaches_real_mealie_and_updates_with_image(bundles, tmp_path):
    sources, _, _ = bundles
    stack = MealieStack(tmp_path, bundled_image=sources[0][0])
    try:
        stack.start()
        slug = stack.recipe()
        assert stack.submit(slug)["status"] == "processed"
        recipe = stack.get(slug)
        assert recipe["nutrition"]["calories"] == "360"
        old_hash = recipe["extras"]["calorie_estimator_hash"]
        cache_before = stack.cache_rows()
        assert cache_before
        override = stack.path / "isolation.json"
        configuration = json.loads(override.read_text(encoding="utf-8"))
        configuration["services"]["calorie-estimator-test"]["image"] = sources[1][0]
        override.write_text(json.dumps(configuration), encoding="utf-8")
        stack.restart_app()
        assert stack.cache_rows() == cache_before
        assert stack.catalog_info()["dataset_version"] == "synthetic-bundled-v2"
        assert stack.submit(slug, "webhook")["status"] == "processed"
        recipe = stack.get(slug)
        assert recipe["nutrition"]["calories"] == "400"
        assert recipe["extras"]["calorie_estimator_hash"] != old_hash
    finally:
        stack.close()


@pytest.mark.skipif(
    os.getenv("RUN_BEDCA_IMAGE_REAL") != "1",
    reason="Set RUN_BEDCA_IMAGE_REAL=1 after building a local image with real BEDCA",
)
def test_real_bedca_image_works_in_mealie_without_source_mount(tmp_path):
    image = os.getenv("BEDCA_BUNDLED_TEST_IMAGE", "mealie-enricher:bedca")
    stack = MealieStack(tmp_path, bundled_image=image)
    try:
        stack.start()
        metadata = stack.catalog_info()
        assert metadata["food_count"] == 957
        assert metadata["food_value_count"] == 31166
        slug = stack.recipe([stack.ingredient(name="Arroz integral", note="en crudo")])
        record = stack.submit(slug)
        assert record["status"] == "processed", record
        recipe = stack.get(slug)
        assert recipe["nutrition"]["calories"] == "384"
        assert recipe["nutrition"]["proteinContent"] == "8"
        assert json.loads(recipe["extras"]["calorie_estimator_catalog"])[0]["id"] == "bedca:904"
        script = (
            "from pathlib import Path; "
            "assert len(list(Path('/opt/bedca/source').glob('*.csv')))==3; "
            "assert not Path('/app/catalogs/catalogos.duckdb').exists()"
        )
        stack.run("exec", "-T", "calorie-estimator-test", "python", "-c", script)
    finally:
        stack.close()
