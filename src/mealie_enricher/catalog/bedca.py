"""Import an external BEDCA CSV export without redistributing its contents."""

import csv
import hashlib
import io
import json
import math
import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import duckdb

from .schema import NUTRIENT_FIELDS, SCHEMA_SQL, SCHEMA_VERSION
from .text import food_states, normalize_name

SOURCE = "bedca"
ATTRIBUTION = "AESAN / BEDCA, Base de Datos Española de Composición de Alimentos, v1.0 (2010)"
SOURCE_URL = "https://www.bedca.net/"
EXPORT_URL = "https://github.com/TerjeRu/bedca-database"
_MASS_UNITS = {"g": 1.0, "mg": 0.001, "ug": 0.000001, "µg": 0.000001, "μg": 0.000001}
_ENERGY_UNITS = {"kJ": 1 / 4.184, "kcal": 1.0}
_BASES = {"W", "WKG", "VM", "D"}
_FIELDS = {
    "ENERC": "kcal_per100g",
    "PROT": "protein_per100g",
    "CHO": "carbs_per100g",
    "FAT": "fat_per100g",
    "FASAT": "saturated_fat_per100g",
    "FATRS": "trans_fat_per100g",
    "FIBT": "fiber_per100g",
    "SUGAR": "sugar_per100g",
    "NA": "sodium_per100g",
    "CHORL": "cholesterol_per100g",
}
_FILES = {
    "bedca_foods.csv": {"f_id", "f_ori_name", "f_eng_name"},
    "bedca_foodvalues.csv": {"f_id", "eur_name", "best_location", "v_unit", "mu_id", "moex"},
    "bedca_units.csv": {"eur_name", "v_unit", "mu_id"},
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _read_export(input_dir: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, str]]:
    tables: dict[str, list[dict[str, str]]] = {}
    hashes = {}
    for filename, required in _FILES.items():
        try:
            data = (input_dir / filename).read_bytes()
            reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), strict=True)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)) or not required.issubset(fields):
                raise ValueError(f"Cabecera CSV inválida en {filename}: faltan columnas requeridas")
            rows = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Fila CSV incompleta o con columnas sobrantes en {filename}")
                rows.append(row)
            if not rows:
                raise ValueError(f"El archivo {filename} no contiene registros")
            tables[filename] = rows
            hashes[filename] = hashlib.sha256(data).hexdigest()
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ValueError(f"No se puede leer el CSV BEDCA {filename}: {exc}") from exc
    return tables, hashes


def _unit_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["eur_name"].strip(), row["v_unit"].strip(), row["mu_id"].strip()


def _validate_unit(code: str, unit: str, basis: str) -> None:
    if not code or basis not in _BASES:
        raise ValueError(f"Componente o base BEDCA inválida: {code!r}, {basis!r}")
    valid = _ENERGY_UNITS if code == "ENERC" else _MASS_UNITS
    if unit not in valid:
        raise ValueError(f"Unidad BEDCA incompatible para {code}: {unit!r}")


def _normalize_value(row: dict[str, str]) -> float | None:
    text = row["best_location"].strip()
    if not text:
        return None
    try:
        numeric = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Valor numérico BEDCA inválido: {text!r}") from exc
    if not numeric.is_finite() or numeric < 0:
        raise ValueError(f"Valor BEDCA no finito o negativo: {text!r}")
    value = float(numeric)
    if not math.isfinite(value) or (numeric != 0 and value == 0):
        raise ValueError(f"Valor numérico BEDCA fuera del intervalo representable: {text!r}")
    code, unit, basis = _unit_key(row)
    # Volume and dry-matter values need density/moisture, which the export does not supply.
    if basis in {"VM", "D"}:
        return None
    factor = (_ENERGY_UNITS if code == "ENERC" else _MASS_UNITS)[unit]
    result = value * factor / (10 if basis == "WKG" else 1)
    if not math.isfinite(result) or (numeric != 0 and result == 0):
        raise ValueError(f"Valor BEDCA fuera del intervalo finito: {text!r}")
    return result


def import_bedca(
    input_dir: Path,
    output: Path,
    dataset_version: str,
    replace: bool = False,
) -> dict[str, Any]:
    """Build and validate a new file, then publish it atomically after closing DuckDB.

    An existing file is replaced only with explicit ``replace=True``. Stop readers
    before replacement on Windows; a failed publication leaves the old file intact.
    """
    input_dir, output = Path(input_dir), Path(output)
    if not dataset_version.strip():
        raise ValueError("La versión del dataset BEDCA no puede estar vacía")
    if output.exists() and not replace:
        raise FileExistsError(f"El catálogo ya existe: {output}; use --replace para sustituirlo")
    tables, hashes = _read_export(input_dir)
    foods = tables["bedca_foods.csv"]
    values = tables["bedca_foodvalues.csv"]
    units = tables["bedca_units.csv"]
    indexed: dict[str, dict[str, str]] = {}
    for food in foods:
        food_id = food["f_id"].strip()
        if not food_id or not normalize_name(food["f_ori_name"]):
            raise ValueError("Identificador o nombre de alimento BEDCA vacío")
        if food_id in indexed:
            raise ValueError(f"Alimento BEDCA duplicado: {food_id}")
        indexed[food_id] = food
    declared = set()
    for row in units:
        key = _unit_key(row)
        _validate_unit(*key)
        if key in declared:
            raise ValueError(f"Combinación de unidad BEDCA duplicada: {key}")
        declared.add(key)
    nutrients: dict[str, dict[str, float | None]] = {food_id: {} for food_id in indexed}
    seen: set[tuple[str, str]] = set()
    base_counts: dict[str, int] = {}
    incompatible = 0
    for row in values:
        food_id = row["f_id"].strip()
        key = _unit_key(row)
        code, _, basis = key
        if food_id not in indexed:
            raise ValueError(f"Componente BEDCA huérfano: alimento {food_id}")
        if (food_id, code) in seen:
            raise ValueError(f"Componente BEDCA duplicado o incompatible: {food_id}/{code}")
        seen.add((food_id, code))
        _validate_unit(*key)
        if key not in declared or row["moex"].strip() != basis:
            raise ValueError(f"Matriz de unidades/bases BEDCA inconsistente: {food_id}/{code}")
        nutrients[food_id][code] = _normalize_value(row)
        base_counts[basis] = base_counts.get(basis, 0) + 1
        incompatible += basis in {"VM", "D"}
    fingerprint = hashlib.sha256(
        _json(
            {
                "schema_version": SCHEMA_VERSION,
                "dataset_version": dataset_version,
                "input_sha256": hashes,
                "source": SOURCE,
            }
        ).encode("utf-8")
    ).hexdigest()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "source_version": "1.0 (2010)",
        "dataset_version": dataset_version,
        "fingerprint": fingerprint,
        "attribution": ATTRIBUTION,
        "source_url": SOURCE_URL,
        "export_url": EXPORT_URL,
        "input_sha256": hashes,
        "food_count": len(foods),
        "food_value_count": len(values),
        "unit_count": len(units),
        "basis_counts": base_counts,
        "incompatible_basis_value_count": incompatible,
        "imported_at": datetime.now(UTC).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    temporary.unlink()  # DuckDB expects a nonexistent path, not an empty file.
    try:
        with duckdb.connect(str(temporary)) as db:
            db.execute("BEGIN TRANSACTION")
            db.execute(SCHEMA_SQL)
            db.executemany(
                "INSERT INTO catalog_metadata VALUES (?, ?)",
                [(key, _json(value)) for key, value in report.items()],
            )
            db.executemany(
                "INSERT INTO raw_foods VALUES (?, ?, ?)",
                [(SOURCE, row["f_id"].strip(), _json(row)) for row in foods],
            )
            db.executemany(
                "INSERT INTO raw_units VALUES (?, ?)",
                [(number, _json(row)) for number, row in enumerate(units, 1)],
            )
            # One bulk statement avoids executing tens of thousands of Python inserts.
            # json_each retains the complete original record, including reference/method fields.
            db.execute(
                "INSERT INTO raw_food_values SELECT CAST(key AS INTEGER) + 1, ?, "
                "trim(value->>'f_id'), trim(value->>'eur_name'), trim(value->>'v_unit'), "
                "trim(value->>'mu_id'), value->>'best_location', value FROM json_each(?)",
                [SOURCE, _json(values)],
            )
            food_rows = []
            token_rows: list[tuple[str, str]] = []
            for food_id, row in indexed.items():
                converted = nutrients[food_id]
                normalized = {field: converted.get(code) for code, field in _FIELDS.items()}
                mono, poly = converted.get("FAMS"), converted.get("FAPU")
                normalized["unsaturated_fat_per100g"] = (
                    mono + poly if mono is not None and poly is not None else None
                )
                if any(
                    value is not None and not math.isfinite(value) for value in normalized.values()
                ):
                    raise ValueError(f"Valor derivado BEDCA no finito en alimento {food_id}")
                states = food_states(row["f_ori_name"] + " " + row["f_eng_name"])
                name, name_en = normalize_name(row["f_ori_name"]), normalize_name(row["f_eng_name"])
                food_rows.append(
                    (
                        f"bedca:{food_id}",
                        SOURCE,
                        food_id,
                        row["f_ori_name"],
                        row["f_eng_name"],
                        next(iter(states)) if len(states) == 1 else None,
                        name,
                        name_en,
                        "100g",
                        *(normalized[field] for field in NUTRIENT_FIELDS),
                    )
                )
                token_rows.extend(
                    (f"bedca:{food_id}", token)
                    for token in sorted(set((name + " " + name_en).split()))
                )
            placeholders = ", ".join("?" for _ in range(9 + len(NUTRIENT_FIELDS)))
            db.executemany(f"INSERT INTO foods VALUES ({placeholders})", food_rows)
            db.executemany("INSERT INTO food_tokens VALUES (?, ?)", token_rows)
            report["normalized_value_count"] = sum(
                value is not None for row in food_rows for value in row[9:]
            )
            db.execute(
                "INSERT INTO catalog_metadata VALUES (?, ?)",
                ["normalized_value_count", _json(report["normalized_value_count"])],
            )
            db.execute("COMMIT")
            db.execute("CHECKPOINT")
        if replace:
            os.replace(temporary, output)
        elif os.name == "nt":
            # Windows rename is atomic and refuses to overwrite an existing target.
            os.rename(temporary, output)
        else:
            # Atomic no-clobber publication also protects against a concurrent import.
            os.link(temporary, output)
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)
        Path(str(temporary) + ".wal").unlink(missing_ok=True)
    return report
