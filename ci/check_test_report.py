"""Reject incomplete CI suites before enabling package publication."""

import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        root = ElementTree.parse(args.report).getroot()
        cases = list(root.iter("testcase"))
        if not cases:
            raise ValueError("El informe no contiene pruebas")
        incomplete = [
            case
            for case in cases
            if any(case.find(kind) is not None for kind in ("skipped", "failure", "error"))
        ]
        if incomplete:
            raise ValueError(
                f"La suite no está completa: {len(incomplete)} pruebas omitidas o fallidas"
            )
    except (OSError, ElementTree.ParseError, ValueError) as error:
        print(f"Error de informe: {error}", file=sys.stderr)
        return 1
    print(f"Suite completa: {len(cases)} pruebas correctas, ninguna omitida")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
