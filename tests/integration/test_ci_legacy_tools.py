"""Trusted generic tools work when an old source checkout has no new helpers."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_trusted_coverage_tool_survives_a_legacy_source_checkout(tmp_path):
    trusted = tmp_path / "runner-temp"
    legacy = tmp_path / "legacy-source"
    trusted.mkdir()
    legacy.mkdir()
    shutil.copyfile(ROOT / "ci/quality.py", trusted / "quality.py")
    (legacy / "coverage.xml").write_text('<coverage lines-covered="96" lines-valid="100"/>')
    result = subprocess.run(
        [sys.executable, str(trusted / "quality.py"), "coverage", "coverage.xml"],
        cwd=legacy,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "96.00%" in result.stdout
    assert not (legacy / "ci/quality.py").exists()


def test_trusted_scanner_uses_its_own_package_and_pin_outside_legacy_checkout(tmp_path):
    trusted = tmp_path / "trusted"
    legacy = tmp_path / "legacy-source"
    legacy.mkdir()
    shutil.copytree(
        ROOT / "ci",
        trusted / "ci",
        ignore=shutil.ignore_patterns("node_modules", "__pycache__", "release-please"),
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(trusted)!r}); from ci.security import scanner_image; print(scanner_image())",
        ],
        cwd=legacy,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "ghcr.io/aquasecurity/trivy:" in result.stdout and "@sha256:" in result.stdout
    assert not (legacy / "ci/security.py").exists()
