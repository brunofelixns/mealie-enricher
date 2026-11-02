"""The publication gate consumes the actual JUnit report, including skips."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


def run_report(tmp_path, body):
    report = tmp_path / "pytest.xml"
    report.write_text(body, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ROOT / "ci/check_test_report.py"), str(report)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )


def test_complete_passing_report_allows_publication(tmp_path):
    result = run_report(
        tmp_path, '<testsuites><testsuite><testcase name="real-mealie"/></testsuite></testsuites>'
    )
    assert result.returncode == 0, result.stderr
    assert "1 pruebas" in result.stdout


@pytest.mark.parametrize("element", ["skipped", "failure", "error"])
def test_skipped_or_failed_tests_block_publication(tmp_path, element):
    result = run_report(
        tmp_path, f'<testsuite><testcase name="docker"><{element}/></testcase></testsuite>'
    )
    assert result.returncode != 0
    assert "no está completa" in result.stderr


@pytest.mark.parametrize("body", ["<testsuite/>", "<not-xml"])
def test_empty_or_corrupt_report_blocks_publication(tmp_path, body):
    result = run_report(tmp_path, body)
    assert result.returncode != 0
    assert "informe" in result.stderr
