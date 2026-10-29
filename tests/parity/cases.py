import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parents[1] / "fixtures" / "parity"


def load_case(case_id: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{case_id}.json").read_text(encoding="utf-8"))


def cases_for(area: str) -> list[dict[str, Any]]:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    return [load_case(case["id"]) for case in manifest["cases"] if case["area"] == area]
