"""Exercise release preparation and publication against disposable Git repositories."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release.py"
VERSION_FILES = ("pyproject.toml", "uv.lock", "Dockerfile")


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=check,
    )


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "--all")
    git(repo, "commit", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def metadata(repo: Path, version: str) -> None:
    (repo / "docker").mkdir(exist_ok=True)
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "mealie-enricher"\nversion = "{version}"\n'
        '\n[tool.example]\nversion = "99.0.0"\n',
        encoding="utf-8",
    )
    (repo / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "other"\nversion = "99.0.0"\n'
        f'\n[[package]]\nname = "mealie-enricher"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (repo / "Dockerfile").write_text(
        f"FROM python:3.14-slim\nARG VERSION={version}\n", encoding="utf-8"
    )
    (repo / "docker/Dockerfile.bedca").write_text(
        f"ARG BASE_IMAGE=mealie-enricher:{version}\nFROM ${{BASE_IMAGE}}\n",
        encoding="utf-8",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "--initial-branch=main")
    git(tmp_path, "config", "user.name", "Release test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / ".gitignore").write_text(".cache/\n", encoding="utf-8")
    metadata(tmp_path, "1.0.0")
    commit(tmp_path, "chore: initial source")
    return tmp_path


def release(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def prepare(repo: Path) -> dict[str, str | bool]:
    release(repo, "prepare", "--output", ".cache/release-plan.json")
    return json.loads((repo / ".cache/release-plan.json").read_text(encoding="utf-8"))


def test_initial_release_ignores_legacy_version_and_unrelated_tags(repo: Path) -> None:
    metadata(repo, "1.13.0")
    source = commit(repo, "feat!: migrated source")
    for tag in ("v1.13.0", "v9.0.0-beta.1", "v01.0.0", "unrelated", "v0.9.0"):
        git(repo, "tag", tag)
    plan = prepare(repo)
    assert plan["version"] == "1.0.0"
    assert plan["source_sha"] == source
    assert plan["tag"] == "v1.0.0"
    assert plan["resumed"] is False
    assert plan["release_sha"] != source
    assert git(repo, "show", "-s", "--format=%B", "HEAD").stdout.strip() == (
        f"chore(release): v1.0.0 [skip ci]\n\nRelease-Source: {source}"
    )
    assert git(repo, "diff", "--name-only", source, "HEAD").stdout.splitlines() == sorted(
        VERSION_FILES
    )
    assert 'version = "99.0.0"' in (repo / "uv.lock").read_text(encoding="utf-8")
    assert "ARG VERSION=1.0.0" in (repo / "Dockerfile").read_text(encoding="utf-8")
    assert "BASE_IMAGE=mealie-enricher:1.13.0" in (repo / "docker/Dockerfile.bedca").read_text(
        encoding="utf-8"
    )
    assert git(repo, "status", "--porcelain").stdout == ""


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("feat: add catalog", "1.1.0"),
        ("fix(api): correct response", "1.1.0"),
        ("docs: explain deployment", "1.0.1"),
        ("refactor!: remove old API", "2.0.0"),
        ("fix(api)!: change schema", "2.0.0"),
        (
            "chore: migrate\n\nDetails on multiple lines.\n\nBREAKING CHANGE: old API removed",
            "2.0.0",
        ),
        ("docs: describe feat: without conventional subject", "1.0.1"),
        ("chore: document\n\nThis mentions BREAKING CHANGE: in prose", "1.0.1"),
        ("feat: text with `echo unsafe` and $(echo unsafe)", "1.1.0"),
    ],
)
def test_commit_conventions_control_version(repo: Path, message: str, expected: str) -> None:
    git(repo, "tag", "v1.0.0")
    source = commit(repo, message)
    plan = prepare(repo)
    assert plan["version"] == expected
    assert plan["source_sha"] == source
    for file in VERSION_FILES:
        assert expected in (repo / file).read_text(encoding="utf-8")


def test_highest_bump_wins_across_all_unreleased_commits(repo: Path) -> None:
    git(repo, "tag", "v1.0.0")
    commit(repo, "feat!: break contract")
    commit(repo, "feat: add option")
    commit(repo, "docs: latest note")
    assert prepare(repo)["version"] == "2.0.0"


def test_minor_bump_skips_reserved_legacy_version_without_moving_its_tag(repo: Path) -> None:
    legacy = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "tag", "v1.13.0", legacy)
    metadata(repo, "1.12.4")
    commit(repo, "chore: own release metadata")
    git(repo, "tag", "v1.12.4")
    commit(repo, "feat: next feature")
    plan = prepare(repo)
    assert plan["version"] == "1.13.1"
    assert plan["tag"] == "v1.13.1"
    assert git(repo, "rev-parse", "v1.13.0").stdout.strip() == legacy


def test_matching_metadata_tags_source_without_an_empty_commit(repo: Path) -> None:
    source = git(repo, "rev-parse", "HEAD").stdout.strip()
    plan = prepare(repo)
    assert plan["release_sha"] == source
    assert plan["source_sha"] == source
    assert plan["version"] == "1.0.0"
    assert git(repo, "cat-file", "-t", "v1.0.0").stdout.strip() == "commit"
    assert prepare(repo) == {**plan, "resumed": True}


def test_rerun_of_old_source_recovers_identical_bot_commit(repo: Path) -> None:
    git(repo, "tag", "v1.0.0")
    source = commit(repo, "feat: next release")
    first = prepare(repo)
    git(repo, "reset", "--hard", source)
    second = prepare(repo)
    assert second == {**first, "resumed": True}
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == first["release_sha"]
    assert git(repo, "show", "-s", "--format=%an <%ae>", "HEAD").stdout.strip() == (
        "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
    )
    assert (
        git(repo, "show", "-s", "--format=%cI", "HEAD").stdout
        == git(repo, "show", "-s", "--format=%cI", source).stdout
    )


def test_bot_commit_is_deterministic_even_if_recovery_tag_is_missing(repo: Path) -> None:
    git(repo, "tag", "v1.0.0")
    source = commit(repo, "fix: repair")
    first = prepare(repo)
    git(repo, "tag", "-d", "v1.1.0")
    git(repo, "reset", "--hard", source)
    assert prepare(repo)["release_sha"] == first["release_sha"]


@pytest.mark.parametrize("file", VERSION_FILES)
def test_malformed_metadata_fails_without_changing_source(repo: Path, file: str) -> None:
    (repo / file).write_text("invalid metadata\n", encoding="utf-8")
    source = commit(repo, "chore: corrupt metadata")
    result = release(repo, "prepare", "--output", ".cache/plan.json", check=False)
    assert result.returncode != 0
    assert "metadata" in result.stderr.lower()
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == source
    assert git(repo, "status", "--porcelain").stdout == ""
    assert git(repo, "tag").stdout == ""


@pytest.mark.parametrize("staged", [False, True])
def test_dirty_worktree_is_rejected_without_committing_changes(repo: Path, staged: bool) -> None:
    (repo / "notes.txt").write_text("user work\n", encoding="utf-8")
    if staged:
        git(repo, "add", "notes.txt")
    source = git(repo, "rev-parse", "HEAD").stdout
    before = git(repo, "status", "--porcelain").stdout
    result = release(repo, "prepare", "--output", ".cache/plan.json", check=False)
    assert result.returncode != 0
    assert "dirty" in result.stderr.lower()
    assert git(repo, "status", "--porcelain").stdout == before
    assert git(repo, "rev-parse", "HEAD").stdout == source


def test_conflicting_version_tag_is_rejected_without_checkout_changes(repo: Path) -> None:
    git(repo, "checkout", "--orphan", "unrelated")
    other = commit(repo, "chore: unrelated history")
    git(repo, "tag", "v1.0.0", other)
    git(repo, "checkout", "main")
    source = git(repo, "rev-parse", "HEAD").stdout
    result = release(repo, "prepare", "--output", ".cache/plan.json", check=False)
    assert result.returncode != 0
    assert "conflict" in result.stderr.lower()
    assert git(repo, "rev-parse", "HEAD").stdout == source
    assert git(repo, "status", "--porcelain").stdout == ""


def test_recovery_marker_cannot_claim_a_commit_with_unrelated_tree(repo: Path) -> None:
    git(repo, "tag", "v1.0.0")
    source = commit(repo, "feat: next")
    (repo / "unexpected.txt").write_text("should not be released", encoding="utf-8")
    fake = commit(repo, f"chore(release): v1.1.0 [skip ci]\n\nRelease-Source: {source}")
    git(repo, "tag", "v1.1.0", fake)
    git(repo, "reset", "--hard", source)
    result = release(repo, "prepare", "--output", ".cache/plan.json", check=False)
    assert result.returncode != 0
    assert "conflict" in result.stderr.lower()
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == source


def remote_for(repo: Path) -> Path:
    remote = repo / ".cache" / "remote.git"
    git(repo, "init", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "origin", "HEAD:refs/heads/main", "--tags")
    return remote


def test_atomic_push_and_retry_after_success(repo: Path) -> None:
    git(repo, "tag", "v1.0.0")
    commit(repo, "feat: next")
    remote = remote_for(repo)
    plan = prepare(repo)
    for _ in range(2):
        result = release(repo, "push", "--plan", ".cache/release-plan.json")
        assert json.loads(result.stdout)["superseded"] is False
    assert git(remote, "rev-parse", "refs/heads/main").stdout.strip() == plan["release_sha"]
    assert git(remote, "rev-parse", "refs/tags/v1.1.0").stdout.strip() == plan["release_sha"]
    git(repo, "reset", "--hard", str(plan["source_sha"]))
    assert prepare(repo) == {**plan, "resumed": True}


def test_remote_advance_supersedes_stale_run_without_pushing(repo: Path) -> None:
    git(repo, "tag", "v1.0.0")
    source = commit(repo, "feat: next")
    remote = remote_for(repo)
    later = commit(repo, "docs: concurrent commit")
    git(repo, "push", "origin", "HEAD:refs/heads/main")
    git(repo, "reset", "--hard", source)
    prepare(repo)
    output = repo / ".cache" / "github-output.txt"
    result = release(
        repo, "push", "--plan", ".cache/release-plan.json", "--github-output", str(output)
    )
    assert json.loads(result.stdout)["superseded"] is True
    assert "superseded=true\n" in output.read_text(encoding="utf-8")
    assert git(remote, "rev-parse", "refs/heads/main").stdout.strip() == later
    assert git(remote, "tag", "--list", "v1.1.0").stdout == ""


def test_tag_rejection_does_not_partially_push_branch(repo: Path) -> None:
    git(repo, "tag", "v1.0.0")
    source = commit(repo, "feat: next")
    remote = remote_for(repo)
    git(remote, "update-ref", "refs/tags/v1.1.0", source)
    prepare(repo)
    result = release(repo, "push", "--plan", ".cache/release-plan.json", check=False)
    assert result.returncode != 0
    assert git(remote, "rev-parse", "refs/heads/main").stdout.strip() == source
    assert git(remote, "rev-parse", "refs/tags/v1.1.0").stdout.strip() == source


def test_remote_race_during_push_cannot_overwrite_main_or_publish_tag(repo: Path) -> None:
    git(repo, "tag", "v1.0.0")
    source = commit(repo, "feat: next")
    remote = remote_for(repo)
    later = commit(repo, "docs: concurrent source")
    git(repo, "push", "origin", "HEAD:refs/heads/concurrent")
    git(repo, "reset", "--hard", source)
    prepare(repo)
    hook = remote / "hooks" / "update"
    hook.write_text(
        '#!/bin/sh\nif test "$1" = refs/heads/main; then\n'
        f"  git update-ref refs/heads/main {later} {source} || exit 1\nfi\n",
        encoding="utf-8",
        newline="\n",
    )
    hook.chmod(0o755)
    result = release(repo, "push", "--plan", ".cache/release-plan.json", check=False)
    assert result.returncode != 0
    assert git(remote, "rev-parse", "refs/heads/main").stdout.strip() == later
    assert git(remote, "tag", "--list", "v1.1.0").stdout == ""


def test_push_refuses_changed_head_and_malformed_plan(repo: Path) -> None:
    remote_for(repo)
    plan = prepare(repo)
    commit(repo, "docs: changed after preparation")
    result = release(repo, "push", "--plan", ".cache/release-plan.json", check=False)
    assert result.returncode != 0
    assert "HEAD" in result.stderr
    plan["version"] = "1.0.0\ninjected=true"
    (repo / ".cache/release-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    output = repo / ".cache" / "github-output.txt"
    result = release(
        repo,
        "push",
        "--plan",
        ".cache/release-plan.json",
        "--github-output",
        str(output),
        check=False,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_prepare_writes_validated_github_outputs(repo: Path) -> None:
    output = repo / ".cache" / "github-output.txt"
    output.parent.mkdir(exist_ok=True)
    result = release(
        repo, "prepare", "--output", ".cache/release-plan.json", "--github-output", str(output)
    )
    plan = json.loads(result.stdout)
    assert dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines()) == {
        **{key: str(value) for key, value in plan.items()},
        "resumed": "false",
    }
