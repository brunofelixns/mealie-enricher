"""Immutable DuckDB snapshots with an atomic manifest for each retailer/postal scope."""

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from ..catalog.text import normalize_name
from .models import Product, Snapshot

_SCHEMA_VERSION = 1


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _scope(retailer: str, postal_code: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", retailer) or not re.fullmatch(
        r"[0-9]{5}", postal_code
    ):
        raise ValueError("Invalid retailer or postal-code catalog scope")
    return f"{retailer}-{postal_code}"


def _fingerprint(snapshot: Snapshot) -> str:
    evidence = {
        "retailer": snapshot.retailer,
        "postal_code": snapshot.postal_code,
        "warehouse": snapshot.warehouse,
        "products": sorted((p.evidence() for p in snapshot.products), key=lambda p: p["id"]),
    }
    return hashlib.sha256(_json(evidence).encode()).hexdigest()


def _validate(snapshot: Snapshot) -> None:
    _scope(snapshot.retailer, snapshot.postal_code)
    if not re.fullmatch(r"[0-9]+", snapshot.warehouse):
        raise ValueError("Catalog snapshot has no validated warehouse")
    try:
        observed = datetime.fromisoformat(snapshot.observed_at)
    except ValueError:
        raise ValueError("Catalog snapshot has no valid observation timestamp") from None
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("Catalog observation timestamp must include a timezone")
    if not snapshot.products or len({p.id for p in snapshot.products}) != len(snapshot.products):
        raise ValueError("Catalog snapshot must contain a complete, unique product set")
    for product in snapshot.products:
        if product.retailer != snapshot.retailer:
            raise ValueError("Catalog product retailer does not match snapshot scope")
        if (product.package_quantity is None) != (product.package_unit is None):
            raise ValueError("Catalog package quantity and unit must both be known or unknown")


class CatalogStore:
    def __init__(self, directory: str) -> None:
        self.directory = Path(directory)

    def publish(self, snapshot: Snapshot) -> str:
        """Activate a fully written version; failures never replace the active manifest.

        Historical files retain all observations, including unchanged-price imports.
        The service's process lock serializes writers; readers open immutable files.
        """
        _validate(snapshot)
        scope = _scope(snapshot.retailer, snapshot.postal_code)
        fingerprint = _fingerprint(snapshot)
        version = uuid4().hex
        filename = f"{scope}-{version}.duckdb"
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / f".building-{version}.duckdb"
        destination = self.directory / filename
        manifest_tmp = self.directory / f".manifest-{version}.json"
        metadata = snapshot.model_dump(mode="json", exclude={"products"})
        metadata.update(fingerprint=fingerprint, schema_version=_SCHEMA_VERSION)
        try:
            with duckdb.connect(str(temporary)) as db:
                db.execute("CREATE TABLE snapshot_metadata (metadata JSON NOT NULL)")
                db.execute("INSERT INTO snapshot_metadata VALUES (?)", [_json(metadata)])
                db.execute(
                    "CREATE TABLE products (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, "
                    "normal_name VARCHAR NOT NULL, retailer VARCHAR NOT NULL, brand VARCHAR, "
                    "url VARCHAR, category VARCHAR, package_quantity DECIMAL(18,6), package_unit VARCHAR, "
                    "price DECIMAL(18,4), available BOOLEAN, variable_weight BOOLEAN, drained_quantity DECIMAL(18,6), "
                    "ingredients VARCHAR, nutrition JSON, raw JSON, product_json JSON NOT NULL)"
                )
                db.execute(
                    "CREATE TABLE price_observations (product_id VARCHAR, retailer VARCHAR, "
                    "postal_code VARCHAR, warehouse VARCHAR, observed_at TIMESTAMP, "
                    "price DECIMAL(18,4), currency VARCHAR, available BOOLEAN)"
                )
                for product in snapshot.products:
                    data = product.model_dump(mode="json")
                    db.execute(
                        "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            product.id,
                            product.name,
                            normalize_name(product.name),
                            product.retailer,
                            product.brand,
                            product.url,
                            product.category,
                            data["package_quantity"],
                            product.package_unit,
                            data["price"],
                            product.available,
                            product.variable_weight,
                            data["drained_quantity"],
                            product.ingredients,
                            _json(product.nutrition),
                            _json(product.raw),
                            _json(data),
                        ],
                    )
                    db.execute(
                        "INSERT INTO price_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            product.id,
                            snapshot.retailer,
                            snapshot.postal_code,
                            snapshot.warehouse,
                            datetime.fromisoformat(snapshot.observed_at)
                            .astimezone(UTC)
                            .replace(tzinfo=None),
                            data["price"],
                            "EUR",
                            product.available,
                        ],
                    )
                db.execute("CHECKPOINT")
            # Re-read the completed database before making it visible to readers.
            self._read(temporary, snapshot.retailer, snapshot.postal_code, fingerprint)
            with temporary.open("r+b") as file:
                os.fsync(file.fileno())
            os.replace(temporary, destination)
            manifest = {
                "schema_version": _SCHEMA_VERSION,
                "file": filename,
                "retailer": snapshot.retailer,
                "postal_code": snapshot.postal_code,
                "fingerprint": fingerprint,
            }
            with manifest_tmp.open("x", encoding="utf-8") as file:
                file.write(_json(manifest))
                file.flush()
                os.fsync(file.fileno())
            os.replace(manifest_tmp, self.directory / f"{scope}.json")
        finally:
            temporary.unlink(missing_ok=True)
            manifest_tmp.unlink(missing_ok=True)
        return fingerprint

    def _active(self, retailer: str, postal_code: str) -> tuple[Path, str] | None:
        scope = _scope(retailer, postal_code)
        manifest_path = self.directory / f"{scope}.json"
        if not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            filename = manifest["file"]
            fingerprint = manifest["fingerprint"]
            if (
                manifest["schema_version"] != _SCHEMA_VERSION
                or manifest["retailer"] != retailer
                or manifest["postal_code"] != postal_code
                or not isinstance(filename, str)
                or not re.fullmatch(re.escape(scope) + r"-[0-9a-f]{32}\.duckdb", filename)
                or not isinstance(fingerprint, str)
                or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
            ):
                raise ValueError("Invalid catalog manifest or scope")
        except OSError, KeyError, TypeError, json.JSONDecodeError:
            raise ValueError("Cannot read a valid catalog manifest") from None
        return self.directory / filename, fingerprint

    @staticmethod
    def _read(path: Path, retailer: str, postal_code: str, fingerprint: str) -> Snapshot:
        if not path.is_file():
            raise ValueError("Active catalog snapshot is missing")
        try:
            with duckdb.connect(str(path), read_only=True) as db:
                metadata_rows = db.execute("SELECT metadata FROM snapshot_metadata").fetchall()
                if len(metadata_rows) != 1:
                    raise ValueError("Invalid catalog snapshot metadata")
                data = json.loads(metadata_rows[0][0])
                if data.pop("schema_version", None) != _SCHEMA_VERSION:
                    raise ValueError("Unsupported catalog schema version")
                data["products"] = [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT product_json FROM products ORDER BY id"
                    ).fetchall()
                ]
            snapshot = Snapshot.model_validate(data)
            _validate(snapshot)
            if (
                snapshot.retailer != retailer
                or snapshot.postal_code != postal_code
                or snapshot.fingerprint != fingerprint
                or _fingerprint(snapshot) != fingerprint
            ):
                raise ValueError("Catalog snapshot fingerprint or scope does not match manifest")
            return snapshot
        except duckdb.Error, json.JSONDecodeError, KeyError, TypeError:
            raise ValueError("Cannot read a valid catalog snapshot") from None

    def load(self, retailer: str, postal_code: str) -> Snapshot | None:
        active = self._active(retailer, postal_code)
        return None if active is None else self._read(active[0], retailer, postal_code, active[1])

    def search(self, retailer: str, postal_code: str, name: str, limit: int = 12) -> list[Product]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Catalog candidate limit must be between 1 and 100")
        tokens = sorted(set(normalize_name(name).split()))
        if not tokens:
            return []
        if len(tokens) > 32 or len(name) > 2048:
            raise ValueError("Catalog search contains too many terms")
        active = self._active(retailer, postal_code)
        if active is None:
            return []
        path, _ = active
        if not path.is_file():
            raise ValueError("Active catalog snapshot is missing")
        conditions = " AND ".join("contains(' ' || normal_name || ' ', ?)" for _ in tokens)
        try:
            with duckdb.connect(str(path), read_only=True) as db:
                rows = db.execute(
                    f"SELECT product_json FROM products WHERE available AND {conditions} "
                    "ORDER BY length(normal_name), id LIMIT ?",
                    [*(f" {token} " for token in tokens), limit],
                ).fetchall()
            return [Product.model_validate_json(row[0]) for row in rows]
        except duckdb.Error:
            raise ValueError("Cannot search the active catalog snapshot") from None
