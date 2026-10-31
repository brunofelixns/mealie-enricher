import csv
import json
from pathlib import Path

import duckdb
import pytest


def make_export(path: Path, foods=None, values=None, units=None):
    """A deliberately synthetic BEDCA-shaped export; never copy real records."""
    path.mkdir(parents=True, exist_ok=True)
    foods = foods or [
        {
            "f_id": "1",
            "f_ori_name": "Arroz, crudo",
            "f_eng_name": "Rice, raw",
            "ENERC": "999",
            "ENERC_unit": "kcal",
        },
        {"f_id": "2", "f_ori_name": "Arroz, cocido", "f_eng_name": "Rice, boiled"},
    ]
    values = (
        values
        if values is not None
        else [
            {
                "f_id": "1",
                "eur_name": "ENERC",
                "best_location": "418.4",
                "v_unit": "kJ",
                "mu_id": "W",
                "moex": "W",
                "citation": "Synthetic reference",
            },
            {
                "f_id": "1",
                "eur_name": "PROT",
                "best_location": "5",
                "v_unit": "g",
                "mu_id": "W",
                "moex": "W",
            },
            {
                "f_id": "2",
                "eur_name": "PROT",
                "best_location": "2",
                "v_unit": "g",
                "mu_id": "W",
                "moex": "W",
            },
        ]
    )
    if units is None:
        units = [
            dict(zip(("eur_name", "v_unit", "mu_id"), combo))
            for combo in sorted({(v["eur_name"], v["v_unit"], v["mu_id"]) for v in values})
        ]
    for filename, rows, required in [
        ("bedca_foods.csv", foods, ["f_id", "f_ori_name", "f_eng_name"]),
        (
            "bedca_foodvalues.csv",
            values,
            ["f_id", "eur_name", "best_location", "v_unit", "mu_id", "moex"],
        ),
        ("bedca_units.csv", units, ["eur_name", "v_unit", "mu_id"]),
    ]:
        fields = list(dict.fromkeys(required + [key for row in rows for key in row]))
        with (path / filename).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    return path


def test_import_preserves_raw_and_uses_long_nutrient_basis(tmp_path):
    from mealie_enricher.catalog.bedca import import_bedca
    from mealie_enricher.catalog.store import DuckDbCatalog

    source = make_export(tmp_path / "input")
    output = tmp_path / "catalog.duckdb"
    report = import_bedca(source, output, "synthetic-1")
    assert report["food_count"] == 2
    assert report["food_value_count"] == 3
    with duckdb.connect(str(output), read_only=True) as db:
        food = json.loads(
            db.execute("SELECT raw_json FROM raw_foods WHERE source_id = '1'").fetchone()[0]
        )
        value = json.loads(
            db.execute(
                "SELECT raw_json FROM raw_food_values WHERE nutrient_code = 'ENERC'"
            ).fetchone()[0]
        )
        assert food["ENERC"] == "999"
        assert value["best_location"] == "418.4"
        assert value["citation"] == "Synthetic reference"
        for table in (
            "products",
            "product_nutrients",
            "packages",
            "retailers",
            "stores",
            "price_observations",
        ):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    catalog = DuckDbCatalog(str(output))
    try:
        food = catalog.get("bedca:1")
        assert food.nutrients.kcal_per100g == pytest.approx(100)
        assert food.nutrients.protein_per100g == 5
        assert food.nutrients.sodium_per100g is None
        assert food.state == "raw"
        assert catalog.fingerprint == report["fingerprint"]
        assert "AESAN" in report["attribution"]
        assert len(report["input_sha256"]["bedca_foods.csv"]) == 64
    finally:
        catalog.close()


def test_units_nulls_and_incompatible_bases_are_conservative(tmp_path):
    from mealie_enricher.catalog.bedca import import_bedca
    from mealie_enricher.catalog.store import DuckDbCatalog

    values = [
        {
            "f_id": "1",
            "eur_name": code,
            "best_location": value,
            "v_unit": unit,
            "mu_id": basis,
            "moex": basis,
        }
        for code, value, unit, basis in [
            ("ENERC", "80", "kcal", "W"),
            ("PROT", "2500", "mg", "W"),
            ("FAT", "1000000", "ug", "W"),
            ("NA", "1200", "mg", "WKG"),
            ("CHORL", "50", "mg", "W"),
            ("FIBT", "", "g", "W"),
            ("CHO", "30", "g", "VM"),
            ("SUGAR", "12", "g", "D"),
            ("FAMS", "3", "g", "W"),
            ("FAPU", "", "g", "W"),
            ("FATRS", "0", "g", "W"),
        ]
    ]
    output = tmp_path / "catalog.duckdb"
    import_bedca(make_export(tmp_path / "input", values=values), output, "test")
    catalog = DuckDbCatalog(str(output))
    try:
        nutrients = catalog.get("bedca:1").nutrients
        assert nutrients.kcal_per100g == 80
        assert nutrients.protein_per100g == 2.5
        assert nutrients.fat_per100g == 1
        assert nutrients.sodium_per100g == pytest.approx(0.12)
        assert nutrients.cholesterol_per100g == 0.05
        assert nutrients.fiber_per100g is None
        assert nutrients.carbs_per100g is None
        assert nutrients.sugar_per100g is None
        assert nutrients.unsaturated_fat_per100g is None
        assert nutrients.trans_fat_per100g == 0
    finally:
        catalog.close()


def test_unsaturated_fat_requires_both_components(tmp_path):
    from mealie_enricher.catalog.bedca import import_bedca
    from mealie_enricher.catalog.store import DuckDbCatalog

    values = [
        {
            "f_id": "1",
            "eur_name": code,
            "best_location": value,
            "v_unit": "g",
            "mu_id": "W",
            "moex": "W",
        }
        for code, value in [("FAMS", "3"), ("FAPU", "2")]
    ]
    output = tmp_path / "catalog.duckdb"
    import_bedca(make_export(tmp_path / "input", values=values), output, "test")
    catalog = DuckDbCatalog(str(output))
    try:
        assert catalog.get("bedca:1").nutrients.unsaturated_fat_per100g == 5
    finally:
        catalog.close()


@pytest.mark.parametrize("invalid", ["-1", "-1e-999", "1e-999", "NaN", "inf", "1,5", "unknown"])
def test_invalid_values_do_not_replace_existing_catalog(tmp_path, invalid):
    from mealie_enricher.catalog.bedca import import_bedca

    source = make_export(tmp_path / "input")
    output = tmp_path / "catalog.duckdb"
    import_bedca(source, output, "valid")
    before = output.read_bytes()
    make_export(
        source,
        values=[
            {
                "f_id": "1",
                "eur_name": "PROT",
                "best_location": invalid,
                "v_unit": "g",
                "mu_id": "W",
                "moex": "W",
            }
        ],
    )
    with pytest.raises(ValueError, match="valor|numérico|finito|negativo"):
        import_bedca(source, output, "invalid", replace=True)
    assert output.read_bytes() == before
    assert list(tmp_path.glob("*.tmp*")) == []


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate_food",
        "duplicate_value",
        "orphan",
        "unknown_unit",
        "basis_mismatch",
        "undeclared_unit",
        "missing_file",
        "bad_header",
        "ragged_csv",
    ],
)
def test_malformed_input_is_rejected(tmp_path, problem):
    from mealie_enricher.catalog.bedca import import_bedca

    foods = [{"f_id": "1", "f_ori_name": "Prueba", "f_eng_name": "Test"}]
    values = [
        {
            "f_id": "1",
            "eur_name": "PROT",
            "best_location": "1",
            "v_unit": "g",
            "mu_id": "W",
            "moex": "W",
        }
    ]
    units = [{"eur_name": "PROT", "v_unit": "g", "mu_id": "W"}]
    if problem == "duplicate_food":
        foods *= 2
    if problem == "duplicate_value":
        values *= 2
    if problem == "orphan":
        values[0]["f_id"] = "404"
    if problem == "unknown_unit":
        values[0]["v_unit"] = units[0]["v_unit"] = "spoon"
    if problem == "basis_mismatch":
        values[0]["moex"] = "VM"
    if problem == "undeclared_unit":
        values[0]["v_unit"] = "mg"
    source = make_export(tmp_path / "input", foods, values, units)
    if problem == "missing_file":
        (source / "bedca_units.csv").unlink()
    if problem == "bad_header":
        (source / "bedca_foods.csv").write_text("wrong\n1\n", encoding="utf-8")
    if problem == "ragged_csv":
        with (source / "bedca_foods.csv").open("a", encoding="utf-8") as stream:
            stream.write("2,extra,columns,unexpected\n")
    output = tmp_path / "catalog.duckdb"
    with pytest.raises(ValueError):
        import_bedca(source, output, "test")
    assert not output.exists()


def test_output_protection_and_deterministic_fingerprint(tmp_path):
    from mealie_enricher.catalog.bedca import import_bedca

    source = make_export(tmp_path / "input")
    output = tmp_path / "catalog.duckdb"
    first = import_bedca(source, output, "v1")
    with pytest.raises(FileExistsError):
        import_bedca(source, output, "v2")
    second = import_bedca(source, tmp_path / "other.duckdb", "v1")
    assert first["fingerprint"] == second["fingerprint"]
    third = import_bedca(source, output, "v2", replace=True)
    assert third["fingerprint"] != first["fingerprint"]


def test_derived_overflow_is_rejected_without_publishing(tmp_path):
    from mealie_enricher.catalog.bedca import import_bedca

    values = [
        {
            "f_id": "1",
            "eur_name": code,
            "best_location": "1e308",
            "v_unit": "g",
            "mu_id": "W",
            "moex": "W",
        }
        for code in ("FAMS", "FAPU")
    ]
    output = tmp_path / "catalog.duckdb"
    with pytest.raises(ValueError, match="finito"):
        import_bedca(make_export(tmp_path / "input", values=values), output, "test")
    assert not output.exists()
