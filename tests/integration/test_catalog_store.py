import json
from concurrent.futures import ThreadPoolExecutor

import duckdb
import pytest
from test_bedca_import import make_export


@pytest.fixture
def catalog_path(tmp_path):
    from mealie_enricher.catalog.bedca import import_bedca

    path = tmp_path / "catalog.duckdb"
    import_bedca(make_export(tmp_path / "source"), path, "test")
    return path


def test_search_preserves_all_states_and_matches_complete_normalized_tokens(catalog_path):
    from mealie_enricher.catalog.store import DuckDbCatalog

    catalog = DuckDbCatalog(str(catalog_path))
    try:
        assert {food.id for food in catalog.search("ARRÓZ")} == {"bedca:1", "bedca:2"}
        assert [food.id for food in catalog.search("rice raw")] == ["bedca:1"]
        assert catalog.search("arro") == []
        assert catalog.search("'; DROP TABLE foods; --") == []
        assert catalog.get("bedca:missing") is None
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert all(len(items) == 2 for items in pool.map(catalog.search, ["arroz"] * 12))
    finally:
        catalog.close()


def test_too_many_matches_never_looks_like_unique_food(catalog_path):
    from mealie_enricher.catalog.models import CatalogSearchTooBroad
    from mealie_enricher.catalog.store import DuckDbCatalog

    catalog = DuckDbCatalog(str(catalog_path))
    try:
        with pytest.raises(CatalogSearchTooBroad):
            catalog.search("arroz", limit=1)
        for limit in (0, -1, 101):
            with pytest.raises(ValueError):
                catalog.search("arroz", limit=limit)
    finally:
        catalog.close()


def test_reader_rejects_missing_or_incompatible_files(tmp_path, catalog_path):
    from mealie_enricher.catalog.store import DuckDbCatalog

    with pytest.raises(ValueError, match="existe"):
        DuckDbCatalog(str(tmp_path / "missing.duckdb"))
    with duckdb.connect(str(catalog_path)) as db:
        db.execute("UPDATE catalog_metadata SET value = '999' WHERE key = 'schema_version'")
    with pytest.raises(ValueError, match="versión|esquema"):
        DuckDbCatalog(str(catalog_path))
    invalid = tmp_path / "invalid.duckdb"
    invalid.write_text("not a database", encoding="utf-8")
    with pytest.raises(ValueError, match="catálogo"):
        DuckDbCatalog(str(invalid))


def test_cli_import_inspect_search_and_clean_errors(tmp_path, capsys):
    from mealie_enricher.catalog.cli import main

    source = make_export(tmp_path / "source")
    output = tmp_path / "catalog.duckdb"
    main(
        [
            "import-bedca",
            "--input-dir",
            str(source),
            "--output",
            str(output),
            "--dataset-version",
            "test",
        ]
    )
    assert json.loads(capsys.readouterr().out)["food_count"] == 2
    main(["inspect", "--catalog", str(output)])
    assert json.loads(capsys.readouterr().out)["dataset_version"] == "test"
    main(["search", "--catalog", str(output), "--name", "arroz crudo"])
    assert json.loads(capsys.readouterr().out)[0]["id"] == "bedca:1"
    with pytest.raises(SystemExit) as error:
        main(
            [
                "import-bedca",
                "--input-dir",
                str(source),
                "--output",
                str(output),
                "--dataset-version",
                "test",
            ]
        )
    assert error.value.code == 1
    assert "Error:" in capsys.readouterr().err
