"""Failure and upgrade checks using real local database files."""

import hashlib
import json
import sqlite3
from contextlib import closing

import pytest
from alembic.config import Config

from alembic import command
from mealie_enricher.catalog import bedca
from mealie_enricher.catalog.store import DuckDbCatalog
from mealie_enricher.storage.cache import SqliteCache
from tests.integration.test_bedca_import import make_export


def test_failed_catalog_publication_keeps_previous_file_and_allows_retry(tmp_path, monkeypatch):
    source = make_export(tmp_path / "source")
    output = tmp_path / "catalogs/catalog.duckdb"
    original = bedca.import_bedca(source, output, "synthetic-v1")
    original_hash = hashlib.sha256(output.read_bytes()).digest()

    def reject_publication(*args):
        raise PermissionError("Synthetic publication denied")

    with monkeypatch.context() as patch:
        patch.setattr(bedca.os, "replace", reject_publication)
        with pytest.raises(PermissionError, match="publication denied"):
            bedca.import_bedca(source, output, "synthetic-v2", replace=True)
    assert hashlib.sha256(output.read_bytes()).digest() == original_hash
    assert list(output.parent.iterdir()) == [output]
    catalog = DuckDbCatalog(str(output))
    try:
        assert catalog.fingerprint == original["fingerprint"]
        assert catalog.get("bedca:1").nutrients.kcal_per100g == pytest.approx(100)
    finally:
        catalog.close()

    updated = bedca.import_bedca(source, output, "synthetic-v2", replace=True)
    catalog = DuckDbCatalog(str(output))
    try:
        assert catalog.fingerprint == updated["fingerprint"]
        assert catalog.fingerprint != original["fingerprint"]
    finally:
        catalog.close()


async def test_sqlite_upgrade_preserves_every_legacy_cache_table(tmp_path):
    path = tmp_path / "legacy.db"
    nutrients = json.dumps({"kcalPer100g": 100, "proteinPer100g": None})
    now = 1700000000000
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY);
            INSERT INTO alembic_version VALUES ('0001');
            CREATE TABLE nutrient_cache (food_name TEXT PRIMARY KEY, nutrients TEXT, updated_at BIGINT);
            CREATE TABLE unmatched_foods (food_name TEXT PRIMARY KEY, updated_at BIGINT);
            CREATE TABLE llm_estimate_cache (lookup_key TEXT PRIMARY KEY, grams FLOAT, updated_at BIGINT);
            CREATE TABLE llm_nutrient_cache (food_name TEXT PRIMARY KEY, nutrients TEXT, updated_at BIGINT);
        """)
        db.execute("INSERT INTO nutrient_cache VALUES (?, ?, ?)", ("arroz", nutrients, now))
        db.execute("INSERT INTO unmatched_foods VALUES (?, ?)", ("pendiente", now))
        db.execute("INSERT INTO llm_estimate_cache VALUES (?, ?, ?)", ("pieza|arroz", 80, now))
        db.execute("INSERT INTO llm_nutrient_cache VALUES (?, ?, ?)", ("otro", nutrients, now))
        db.commit()
        tables = ("nutrient_cache", "unmatched_foods", "llm_estimate_cache", "llm_nutrient_cache")
        before = {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in tables}

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", "sqlite:///" + path.as_posix())
    command.upgrade(config, "head")
    with closing(sqlite3.connect(path)) as db:
        for table in tables:
            assert db.execute(f"SELECT * FROM {table}").fetchall() == before[table]
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0002",)
        assert db.execute("SELECT COUNT(*) FROM catalog_resolution_cache").fetchone() == (0,)

    cache = await SqliteCache.open(str(path), 86400000, clock_ms=lambda: now)
    try:
        assert (await cache.get_nutrients("arroz")).protein_per100g is None
        assert await cache.get_grams("pieza", "arroz") == 80
        assert (await cache.get_llm_nutrients("otro")).kcal_per100g == 100
    finally:
        await cache.close()
