"""Small CI policies shared by pull requests and the full-suite gate."""

import argparse
import os
import re
from pathlib import Path
from xml.etree import ElementTree

TITLE = re.compile(
    r"^(feat|fix|refactor|perf|style|test|docs|build|ops|ci|chore|revert)(?:\([^()\r\n]+\))?!?: ([^\r\n]+)$"
)


def check_title(title: str) -> None:
    match = TITLE.fullmatch(title)
    if not match:
        raise ValueError("Usa Conventional Commits: tipo(scope opcional): descripción")
    description = match.group(2)
    if description != description.strip() or description[0].isupper() or description.endswith("."):
        raise ValueError("La descripción debe empezar en minúscula y terminar sin punto")


def check_coverage(path: Path, minimum: float = 95) -> float:
    try:
        root = ElementTree.parse(path).getroot()
        valid = int(root.attrib["lines-valid"])
        covered = int(root.attrib["lines-covered"])
        if valid <= 0 or not 0 <= covered <= valid:
            raise ValueError("Recuento de líneas inválido")
        percentage = 100 * covered / valid
        if percentage < minimum:
            raise ValueError(f"Cobertura {percentage:.2f}% inferior al mínimo {minimum:.2f}%")
        return percentage
    except (ElementTree.ParseError, KeyError, TypeError) as error:
        raise ValueError("Informe de cobertura inválido") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("title")
    coverage = commands.add_parser("coverage")
    coverage.add_argument("path", type=Path)
    coverage.add_argument("--minimum", type=float, default=95)
    coverage.add_argument("--junit", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "title":
            check_title(os.environ.get("PR_TITLE", ""))
            print("Título de PR correcto")
        else:
            percentage = check_coverage(args.path, args.minimum)
            summary = (
                f"### Calidad\n\nCobertura: **{percentage:.2f}%** (mínimo {args.minimum:g}%).\n"
            )
            if args.junit:
                cases = list(ElementTree.parse(args.junit).getroot().iter("testcase"))
                summary += (
                    f"\nSuite: **{len(cases)} pruebas**. El gate rechaza fallos y omisiones.\n"
                )
            print(summary)
            if destination := os.environ.get("GITHUB_STEP_SUMMARY"):
                with Path(destination).open("a", encoding="utf-8") as output:
                    output.write(summary)
    except (OSError, ValueError, ElementTree.ParseError) as error:
        print(str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
