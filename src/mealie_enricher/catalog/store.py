import json
import re
from pathlib import Path
from threading import Lock
from typing import Any

import duckdb

from ..models import NutrientSet
from .models import CatalogFood, CatalogSearchTooBroad
from .schema import NUTRIENT_FIELDS, REQUIRED_COLUMNS, SCHEMA_VERSION
from .text import normalize_name

_SELECT = "id, source, source_id, name, name_en, state, basis, " + ", ".join(NUTRIENT_FIELDS)


class DuckDbCatalog:
    """A version-validated reader with serialized access to its read-only connection."""

    def __init__(self, path: str) -> None:
        if not Path(path).is_file():
            raise ValueError(f"El archivo de catálogo no existe: {path}")
        self._lock = Lock()
        self._closed = False
        try:
            self._db = duckdb.connect(path, read_only=True)
            try:
                columns: dict[str, set[str]] = {}
                for table, column in self._db.execute(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'main'"
                ).fetchall():
                    columns.setdefault(table, set()).add(column)
                for table, required in REQUIRED_COLUMNS.items():
                    if not required.issubset(columns.get(table, set())):
                        raise ValueError(f"Esquema de catálogo inválido: tabla {table}")
                self._metadata = {
                    key: json.loads(value)
                    for key, value in self._db.execute(
                        "SELECT key, value FROM catalog_metadata"
                    ).fetchall()
                }
                if self._metadata.get("schema_version") != SCHEMA_VERSION:
                    raise ValueError("La versión del esquema del catálogo no es compatible")
                fingerprint = self._metadata.get("fingerprint", "")
                if not isinstance(fingerprint, str) or not re.fullmatch(
                    "[0-9a-f]{64}", fingerprint
                ):
                    raise ValueError("El catálogo no contiene una huella de versión válida")
                if not self._metadata.get("dataset_version"):
                    raise ValueError("El catálogo no contiene versión de dataset")
                self.fingerprint: str = fingerprint
            except Exception:
                self._db.close()
                raise
        except (duckdb.Error, json.JSONDecodeError) as exc:
            raise ValueError(f"No se puede abrir el catálogo DuckDB: {exc}") from exc

    def inspect(self) -> dict[str, Any]:
        return dict(self._metadata)

    def _require_open(self) -> None:
        if self._closed:
            raise ValueError("El catálogo está cerrado")

    @staticmethod
    def _food(row: tuple[Any, ...]) -> CatalogFood:
        return CatalogFood(
            id=row[0],
            source=row[1],
            source_id=row[2],
            name=row[3],
            name_en=row[4],
            state=row[5],
            basis=row[6],
            nutrients=NutrientSet(**dict(zip(NUTRIENT_FIELDS, row[7:], strict=True))),
        )

    def search(self, name: str, limit: int = 20) -> list[CatalogFood]:
        """Match whole accent-folded Spanish/English tokens, returning every candidate.

        A result set larger than the bound raises CatalogSearchTooBroad. Callers must
        preserve ambiguity; slicing could make one candidate appear uniquely safe.
        """
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("El límite de candidatos debe estar entre 1 y 100")
        tokens = sorted(set(normalize_name(name).split()))
        if not tokens:
            return []
        if len(tokens) > 32:
            raise CatalogSearchTooBroad("La búsqueda contiene demasiados términos")
        placeholders = ", ".join("?" for _ in tokens)
        with self._lock:
            self._require_open()
            rows = self._db.execute(
                f"SELECT {_SELECT} FROM foods WHERE id IN ("
                f"SELECT food_id FROM food_tokens WHERE token IN ({placeholders}) "
                "GROUP BY food_id HAVING COUNT(DISTINCT token) = ?) ORDER BY id LIMIT ?",
                [*tokens, len(tokens), limit + 1],
            ).fetchall()
        if len(rows) > limit:
            raise CatalogSearchTooBroad(
                f"La búsqueda supera {limit} candidatos; concrete el alimento y su estado"
            )
        return [self._food(row) for row in rows]

    def get(self, id: str) -> CatalogFood | None:
        with self._lock:
            self._require_open()
            row = self._db.execute(f"SELECT {_SELECT} FROM foods WHERE id = ?", [id]).fetchone()
        return self._food(row) if row is not None else None

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._db.close()
                self._closed = True
