"""Explicit catalog preparation; importing never happens during application startup."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb

from .bedca import import_bedca
from .store import DuckDbCatalog


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Importar y consultar catálogos de alimentos")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import-bedca", help="Importar los tres CSV externos de BEDCA")
    importer.add_argument("--input-dir", required=True, type=Path)
    importer.add_argument("--output", required=True, type=Path)
    importer.add_argument("--dataset-version", required=True)
    importer.add_argument("--replace", action="store_true")
    inspector = commands.add_parser("inspect", help="Mostrar versión y procedencia del catálogo")
    inspector.add_argument("--catalog", required=True)
    searcher = commands.add_parser("search", help="Buscar candidatos completos")
    searcher.add_argument("--catalog", required=True)
    searcher.add_argument("--name", required=True)
    searcher.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    result: dict[str, Any] | list[dict[str, Any]]
    try:
        if args.command == "import-bedca":
            result = import_bedca(args.input_dir, args.output, args.dataset_version, args.replace)
        else:
            catalog = DuckDbCatalog(args.catalog)
            try:
                result = (
                    catalog.inspect()
                    if args.command == "inspect"
                    else [
                        food.model_dump(mode="json")
                        for food in catalog.search(args.name, args.limit)
                    ]
                )
            finally:
                catalog.close()
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, duckdb.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
