"""Additional opt-in E2E: real Mealie, real app, DuckDB and SQLite, through HTTP."""

import json
import os
from pathlib import Path

import pytest

from tests.integration.test_docker_smoke import _wait_until
from tests.support.mealie_stack import ROOT, MealieStack, synthetic_catalog

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SMOKE") != "1", reason="Set RUN_DOCKER_SMOKE=1 for isolated Docker E2E"
)


@pytest.fixture(scope="module")
def isolated_mealie(tmp_path_factory):
    stack = MealieStack(tmp_path_factory.mktemp("mealie-real"))
    try:
        stack.start()
        yield stack
    finally:
        stack.close()


@pytest.fixture
def stack(isolated_mealie):
    try:
        yield isolated_mealie
    finally:
        isolated_mealie.clear_recipes()


@pytest.mark.parametrize(
    "note,expected_kcal,expected_protein,expected_id",
    [("en crudo", "360", "8", "bedca:1"), ("ya cocido", "120", "3", "bedca:2")],
)
def test_preparation_and_servings_saved_in_real_mealie(
    stack, note, expected_kcal, expected_protein, expected_id
):
    slug = stack.recipe([stack.ingredient(note=note)])
    record = stack.submit(slug)
    assert record["status"] == "processed", record
    recipe = stack.get(slug)
    assert recipe["nutrition"]["calories"] == expected_kcal
    assert recipe["nutrition"]["proteinContent"] == expected_protein
    assert recipe["nutrition"]["sodiumContent"] is None
    assert json.loads(recipe["extras"]["calorie_estimator_catalog"])[0]["id"] == expected_id
    expected_calorie_tag = "Calorías:Bajas" if note == "ya cocido" else "Calorías:Moderadas"
    assert {tag["name"] for tag in recipe["tags"]} == {expected_calorie_tag, "Digestión:Fácil"}


def test_webhook_recalculates_after_note_and_servings_changes(stack):
    slug = stack.recipe()
    assert stack.submit(slug)["status"] == "processed"
    old_hash = stack.get(slug)["extras"]["calorie_estimator_hash"]
    stack.patch(slug, recipeIngredient=[stack.ingredient(note="ya cocido")], recipeServings=4)
    record = stack.submit(slug, "webhook")
    assert record["status"] == "processed", record
    recipe = stack.get(slug)
    assert recipe["nutrition"]["calories"] == "60"  # 200 g * 120 / 100 / 4.
    assert recipe["nutrition"]["proteinContent"] == "2"  # Original integer rounding.
    assert recipe["extras"]["calorie_estimator_hash"] != old_hash
    assert json.loads(recipe["extras"]["calorie_estimator_catalog"])[0]["id"] == "bedca:2"
    assert stack.submit(slug, "webhook")["status"] == "skipped"


def test_tag_translation_preserves_personal_metadata_and_nutrition(stack):
    slug = stack.recipe(extras={"personal": "conservar"}, description="Mi descripción")
    assert stack.submit(slug)["status"] == "processed"
    original = stack.get(slug)
    tags = []
    for name in ("Mi favorita", "Calories:Moderate", "Digest:Easy"):
        response = stack.mealie.post("/api/organizers/tags", json={"name": name})
        response.raise_for_status()
        tags.append(response.json())
    extras = {
        **original["extras"],
        "calorie_estimator_tags": json.dumps([tag["slug"] for tag in tags[1:]]),
    }
    stack.patch(slug, tags=tags, extras=extras)
    record = stack.submit(slug, "webhook")
    assert record["status"] == "tags-added", record
    recipe = stack.get(slug)
    assert recipe["nutrition"] == original["nutrition"]
    assert recipe["extras"]["personal"] == "conservar"
    assert (
        recipe["extras"]["calorie_estimator_hash"] == original["extras"]["calorie_estimator_hash"]
    )
    assert recipe["description"] == "Mi descripción"
    assert {tag["name"] for tag in recipe["tags"]} == {
        "Mi favorita",
        "Calorías:Moderadas",
        "Digestión:Fácil",
    }
    assert stack.submit(slug, "webhook")["status"] == "skipped"


def test_webhook_preserves_manual_nutrition_but_explicit_estimate_replaces_it(stack):
    slug = stack.recipe(nutrition={"calories": "777", "proteinContent": "31"})
    manual = stack.get(slug)["nutrition"]
    record = stack.submit(slug, "webhook")
    assert record["status"] == "manual", record
    assert stack.get(slug)["nutrition"] == manual
    assert stack.submit(slug)["status"] == "processed"
    assert stack.get(slug)["nutrition"]["calories"] == "360"


@pytest.mark.parametrize("unit", ["ml", "unidad"])
def test_unknown_mass_clears_previous_automatic_nutrition(stack, unit):
    slug = stack.recipe()
    assert stack.submit(slug)["status"] == "processed"
    stack.patch(slug, recipeIngredient=[stack.ingredient(unit=unit)])
    record = stack.submit(slug, "webhook")
    assert record["status"] == "processed", record
    assert record["estimate"]["matchedCount"] == 0
    assert record["estimate"]["unmatchedCount"] == 1
    recipe = stack.get(slug)
    assert all(value is None for value in recipe["nutrition"].values())
    assert recipe["extras"]["calorie_estimator_total_kcal"] == ""
    assert {tag["name"] for tag in recipe["tags"]} == {"Digestión:Desconocida"}


def test_removing_all_ingredients_clears_automatic_nutrition(stack):
    slug = stack.recipe()
    assert stack.submit(slug)["status"] == "processed"
    stack.patch(slug, recipeIngredient=[])
    record = stack.submit(slug, "webhook")
    assert record["status"] == "processed", record
    recipe = stack.get(slug)
    assert recipe["nutrition"]["calories"] is None
    assert recipe["nutrition"]["proteinContent"] is None
    assert json.loads(recipe["extras"]["calorie_estimator_catalog"]) == []
    assert {tag["name"] for tag in recipe["tags"]} == {"Digestión:Desconocida"}


def test_partial_sum_remains_visible_with_unmatched_ingredient(stack):
    slug = stack.recipe([stack.ingredient(), stack.ingredient(note="", quantity=50)])
    record = stack.submit(slug)
    assert record["status"] == "processed", record
    assert record["estimate"]["matchedCount"] == 1
    assert record["estimate"]["unmatchedCount"] == 1
    recipe = stack.get(slug)
    assert recipe["nutrition"]["calories"] == "360"  # Preserved partial-sum limitation C22.
    assert json.loads(recipe["extras"]["calorie_estimator_unmatched"]) == ["Arroz"]


def test_backfill_handles_resolved_manual_and_ambiguous_recipes(stack):
    resolved = stack.recipe()
    manual = stack.recipe(nutrition={"calories": "555"})
    ambiguous = stack.recipe([stack.ingredient(note="")])
    before = {record["id"] for record in stack.history()}
    assert stack.app.post("/backfill", json={}).status_code == 202

    def completed():
        records = {
            record["slug"]: record
            for record in stack.history()
            if record["id"] not in before and record["trigger"] == "backfill"
        }
        return (
            records
            if set(records) == {resolved, manual, ambiguous}
            and all(record["status"] != "running" for record in records.values())
            else None
        )

    records = _wait_until(completed)
    assert records[resolved]["status"] == "processed"
    assert records[manual]["status"] == "manual"
    assert records[ambiguous]["status"] == "processed"
    assert records[ambiguous]["estimate"]["unmatchedCount"] == 1
    assert stack.get(resolved)["nutrition"]["calories"] == "360"
    assert stack.get(manual)["nutrition"]["calories"] == "555"
    assert stack.get(ambiguous)["nutrition"]["calories"] is None


def test_real_mealie_404_is_reported_and_next_request_recovers(stack):
    record = stack.submit("missing-synthetic-recipe")
    assert record["status"] == "error", record
    assert "Mealie API 404" in record["error"]
    slug = stack.recipe()
    assert stack.submit(slug)["status"] == "processed"
    response = stack.app.get("/estimator/history")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert stack.get(slug)["nutrition"]["calories"] == "360"


def test_restart_preserves_cache_catalog_and_mealie_but_resets_history(stack):
    slug = stack.recipe()
    assert stack.submit(slug)["status"] == "processed"
    recipe_before, cache_before, catalog_before = (
        stack.get(slug),
        stack.cache_rows(),
        stack.catalog_info(),
    )
    assert cache_before
    stack.restart_app()
    assert stack.history() == []  # History is deliberately in memory.
    assert stack.get(slug)["nutrition"] == recipe_before["nutrition"]
    assert stack.cache_rows() == cache_before
    assert stack.catalog_info() == catalog_before
    assert stack.submit(slug)["status"] == "processed"
    assert stack.cache_rows() == cache_before  # A cache hit does not rewrite its timestamp.
    assert stack.get(slug)["nutrition"]["calories"] == "360"


def test_catalog_replacement_recalculates_existing_recipe(stack):
    slug = stack.recipe()
    assert stack.submit(slug)["status"] == "processed"
    original_hash = stack.get(slug)["extras"]["calorie_estimator_hash"]
    try:
        stack.run("stop", "calorie-estimator-test")
        synthetic_catalog(stack.source, raw_kcal=400)
        stack.values["BEDCA_DATASET_VERSION"] = "synthetic-real-mealie-v2"
        stack.save_env()
        refused = stack.import_catalog(check=False)
        assert refused.returncode != 0
        assert "--replace" in refused.stderr
        report = json.loads(stack.import_catalog(replace=True).stdout)
        assert report["dataset_version"] == "synthetic-real-mealie-v2"
        stack.restart_app()
        record = stack.submit(slug, "webhook")
        assert record["status"] == "processed", record
        recipe = stack.get(slug)
        assert recipe["nutrition"]["calories"] == "400"
        assert recipe["extras"]["calorie_estimator_hash"] != original_hash
    finally:
        stack.run("stop", "calorie-estimator-test")
        synthetic_catalog(stack.source)
        stack.values["BEDCA_DATASET_VERSION"] = "synthetic-real-mealie-v1"
        stack.save_env()
        stack.import_catalog(replace=True)
        stack.restart_app()


@pytest.mark.skipif(
    os.getenv("RUN_REAL_BEDCA") != "1", reason="Set RUN_REAL_BEDCA=1 with local external BEDCA CSV"
)
def test_local_real_bedca_export_is_imported_and_written_to_real_mealie(stack):
    source = Path(os.getenv("BEDCA_REAL_TEST_DIR", str(ROOT / "data/bedca"))).resolve()
    for filename in ("bedca_foods.csv", "bedca_foodvalues.csv", "bedca_units.csv"):
        assert (source / filename).is_file(), f"Missing external export: {source / filename}"
    try:
        stack.run("stop", "calorie-estimator-test")
        stack.values["BEDCA_INPUT_DIR"] = source.as_posix()
        stack.values["BEDCA_DATASET_VERSION"] = "local-real-bedca-e2e"
        stack.save_env()
        report = json.loads(stack.import_catalog(replace=True).stdout)
        assert report["food_count"] == 957
        assert report["food_value_count"] == 31166
        stack.restart_app()
        slug = stack.recipe([stack.ingredient(name="Arroz integral", note="en crudo")])
        record = stack.submit(slug)
        assert record["status"] == "processed", record
        recipe = stack.get(slug)
        # Source 904: 1607.11 kJ / 4.184 = 384.108... kcal, protein 7.5 g / 100 g.
        assert recipe["nutrition"]["calories"] == "384"
        assert recipe["nutrition"]["proteinContent"] == "8"
        trace = json.loads(recipe["extras"]["calorie_estimator_catalog"])[0]
        assert trace["id"] == "bedca:904"
        assert trace["source"] == "bedca"
        assert trace["state"] == "raw"
    finally:
        stack.run("stop", "calorie-estimator-test")
        stack.values["BEDCA_INPUT_DIR"] = stack.source.as_posix()
        stack.values["BEDCA_DATASET_VERSION"] = "synthetic-real-mealie-v1"
        stack.save_env()
        stack.import_catalog(replace=True)
        stack.restart_app()
