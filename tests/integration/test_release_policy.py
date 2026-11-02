"""Exercise release policy against real, disposable Git repositories."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "ci/release_policy.py"


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def metadata(root, version):
    (root / "pyproject.toml").write_text(
        f'[project]\nname="mealie-enricher"\nversion="{version}"\n', encoding="utf-8"
    )
    (root / "uv.lock").write_text(
        f'[[package]]\nname="mealie-enricher"\nversion="{version}"\n'
        '\n[[package]]\nname="other"\nversion="99.0.0"\n',
        encoding="utf-8",
    )
    (root / "Dockerfile").write_text(f"ARG VERSION={version}\n", encoding="utf-8")
    (root / ".release-please-manifest.json").write_text(
        json.dumps({".": version}), encoding="utf-8"
    )


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "--initial-branch=main")
    git(tmp_path, "config", "user.name", "Release test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    metadata(tmp_path, "1.0.0")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: initial")
    git(tmp_path, "tag", "v1.0.0")
    git(tmp_path, "tag", "v1.13.0")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return tmp_path


def run(root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )


@pytest.mark.parametrize(
    "message,expected",
    [
        ("feat: feature", "1.1.0"),
        ("fix(api): fix behavior", "1.1.0"),
        ("ops(ci): update workflow", "1.0.1"),
        ("docs: explain workflow", "1.0.1"),
        ("feat!: incompatible", "2.0.0"),
        ("refactor: change\n\nBREAKING CHANGE: incompatible", "2.0.0"),
    ],
)
def test_plan_preserves_version_policy_without_mutating_git(repo, message, expected):
    git(repo, "commit", "--allow-empty", "-m", message)
    before = (
        git(repo, "rev-parse", "HEAD"),
        git(repo, "status", "--porcelain"),
        git(repo, "tag", "--list"),
    )
    result = run(repo, "plan")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["next_version"] == expected
    assert before == (
        git(repo, "rev-parse", "HEAD"),
        git(repo, "status", "--porcelain"),
        git(repo, "tag", "--list"),
    )


def test_plan_reserves_the_legacy_version(repo):
    git(repo, "tag", "v1.12.4")
    git(repo, "commit", "--allow-empty", "-m", "feat: next")
    result = run(repo, "plan")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["next_version"] == "1.13.1"


def test_verify_accepts_matching_tag_metadata_and_main(repo):
    result = run(repo, "verify", "--tag", "v1.0.0")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["sha"] == git(repo, "rev-parse", "HEAD")


def test_resolve_checks_metadata_without_checking_out_release(repo):
    original = git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "--allow-empty", "-m", "docs: later")
    result = run(repo, "resolve", "--tag", "v1.0.0")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["sha"] == original
    assert git(repo, "rev-parse", "HEAD") != original


def test_resolve_rejects_unmerged_code_before_executing_its_validator(repo):
    git(repo, "checkout", "-b", "untrusted")
    metadata(repo, "1.0.1")
    (repo / "ci").mkdir()
    (repo / "ci/release_policy.py").write_text("raise SystemExit(0)", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "chore: unmerged")
    git(repo, "tag", "v1.0.1")
    result = run(repo, "resolve", "--tag", "v1.0.1")
    assert result.returncode != 0
    assert "main" in result.stderr


@pytest.mark.parametrize("proposed,valid", [("1.1.0", True), ("1.0.1", False)])
def test_release_pr_version_must_cover_the_current_base_changes(repo, proposed, valid):
    git(repo, "commit", "--allow-empty", "-m", "feat: change before release")
    base = git(repo, "rev-parse", "HEAD")
    metadata(repo, proposed)
    result = run(repo, "proposal", "--base", base)
    assert (result.returncode == 0) is valid
    if not valid:
        assert "propuesta" in result.stderr


@pytest.mark.parametrize(
    "file", ["pyproject.toml", "uv.lock", "Dockerfile", ".release-please-manifest.json"]
)
def test_verify_rejects_metadata_disagreement(repo, file):
    path = repo / file
    path.write_text(path.read_text().replace("1.0.0", "1.0.1"), encoding="utf-8")
    result = run(repo, "verify", "--tag", "v1.0.0")
    assert result.returncode != 0
    assert "metadatos" in result.stderr


@pytest.mark.parametrize("tag", ["v1.13.0", "v01.0.0", "main", "v1.0.0\nfoo"])
def test_verify_rejects_invalid_and_legacy_tags(repo, tag):
    assert run(repo, "verify", "--tag", tag).returncode != 0


def test_verify_rejects_tag_outside_main(repo):
    git(repo, "checkout", "-b", "other")
    metadata(repo, "1.0.1")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "chore: isolated")
    git(repo, "tag", "v1.0.1")
    result = run(repo, "verify", "--tag", "v1.0.1")
    assert result.returncode != 0
    assert "main" in result.stderr


def test_verify_rejects_wrong_checked_out_commit(repo):
    git(repo, "commit", "--allow-empty", "-m", "docs: later")
    result = run(repo, "verify", "--tag", "v1.0.0")
    assert result.returncode != 0
    assert "commit" in result.stderr


@pytest.mark.parametrize("version,expected", [("1.0.0", False), ("1.1.0", True)])
def test_aliases_ignore_legacy_drafts_and_prereleases(repo, version, expected):
    releases = [
        {"tag_name": tag, "draft": draft, "prerelease": prerelease}
        for tag, draft, prerelease in [
            ("v1.0.0", False, False),
            ("v1.1.0", False, False),
            ("v1.13.0", False, False),
            ("v9.0.0", True, False),
            ("v8.0.0", False, True),
        ]
    ]
    path = repo / "releases.json"
    path.write_text(json.dumps(releases), encoding="utf-8")
    result = run(repo, "aliases", "--version", version, "--releases", str(path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["publish_aliases"] is expected
