"""Prepare deterministic local releases and publish their Git refs atomically.

Only stable tags belonging to the new 1.0.0 release series are considered. The
historical v1.13.0 tag is deliberately excluded from that series.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
VERSION_FILES = ("pyproject.toml", "uv.lock", "Dockerfile")
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


class ReleaseError(Exception):
    """A release cannot safely proceed."""


def git(*args: str, input_text: str | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        input=input_text.encode("utf-8") if input_text is not None else None,
        capture_output=True,
        env={**os.environ, **(env or {})},
        check=False,
    )
    if result.returncode:
        raise ReleaseError(f"git {args[0]} failed: {result.stderr.decode('utf-8').strip()}")
    return result.stdout.decode("utf-8").strip()


def version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise ReleaseError(f"Invalid stable version in metadata: {value!r}")
    return int(match[1]), int(match[2]), int(match[3])


def release_message(version: str, source: str) -> str:
    return f"chore(release): v{version} [skip ci]\n\nRelease-Source: {source}"


def own_tags() -> dict[str, str]:
    tags = {}
    for tag in git("tag", "--list").splitlines():
        if tag == "v1.13.0" or not tag.startswith("v") or not VERSION_RE.fullmatch(tag[1:]):
            continue
        if version_tuple(tag[1:]) < (1, 0, 0):
            continue
        tags[tag] = git("rev-parse", f"refs/tags/{tag}^{{commit}}")
    return tags


def select_version(source: str, tags: dict[str, str]) -> tuple[str, bool]:
    current = [tag[1:] for tag, target in tags.items() if target == source]
    if current:
        return max(current, key=version_tuple), True

    recovered = []
    for tag, target in tags.items():
        if git("show", "-s", "--format=%P", target) != source:
            continue
        if git("show", "-s", "--format=%B", target) == release_message(tag[1:], source):
            recovered.append(tag[1:])
    if recovered:
        if len(recovered) != 1:
            raise ReleaseError("Conflicting release tags claim the same source")
        return recovered[0], True

    reachable = set(git("tag", "--merged", source).splitlines())
    previous = [tag[1:] for tag in tags if tag in reachable]
    if not previous:
        return "1.0.0", False
    version = max(previous, key=version_tuple)
    messages = git("log", "--format=%B%x00", f"refs/tags/v{version}..{source}")
    bump = 0
    for message in messages.split("\0"):
        message = message.strip()
        if not message:
            continue
        subject = message.splitlines()[0]
        if re.match(r"^[a-zA-Z][\w-]*(?:\([^\r\n]+\))?!:", subject) or re.search(
            r"(?m)^BREAKING CHANGE:[ \t]*\S", message
        ):
            bump = max(bump, 2)
        elif re.match(r"^(?:feat|fix)(?:\([^\r\n]+\))?:", subject):
            bump = max(bump, 1)
    major, minor, patch = version_tuple(version)
    if bump == 2:
        candidate = f"{major + 1}.0.0"
    elif bump == 1:
        candidate = f"{major}.{minor + 1}.0"
    else:
        candidate = f"{major}.{minor}.{patch + 1}"
    return "1.13.1" if candidate == "1.13.0" else candidate, False


def replace_version_line(section: str, version: str) -> str:
    pattern = re.compile(r"""(?m)^([ \t]*version[ \t]*=[ \t]*)(["'])([^"'\r\n]+)\2""")
    matches = list(pattern.finditer(section))
    if len(matches) != 1:
        raise ReleaseError("Expected exactly one version assignment in metadata section")
    version_tuple(matches[0][3])
    return pattern.sub(lambda match: f"{match[1]}{match[2]}{version}{match[2]}", section)


def version_contents(version: str) -> dict[str, str]:
    """Validate and replace only the three release metadata assignments."""
    contents = {name: Path(name).read_bytes().decode("utf-8") for name in VERSION_FILES}
    try:
        project = tomllib.loads(contents["pyproject.toml"])["project"]
        if project["name"] != "mealie-enricher":
            raise ValueError("unexpected project name")
        version_tuple(project["version"])
        packages = [
            package
            for package in tomllib.loads(contents["uv.lock"])["package"]
            if package.get("name") == "mealie-enricher"
        ]
        if len(packages) != 1:
            raise ValueError("expected one mealie-enricher package")
        version_tuple(packages[0]["version"])

        pattern = re.compile(r"(?ms)^\[project\][ \t]*\r?\n.*?(?=^\[|\Z)")
        contents["pyproject.toml"], count = pattern.subn(
            lambda match: replace_version_line(match[0], version), contents["pyproject.toml"]
        )
        if count != 1:
            raise ValueError("missing project section")
        package_pattern = re.compile(r"(?ms)^\[\[package\]\][ \t]*\r?\n.*?(?=^\[\[package\]\]|\Z)")

        def replace_package(match: re.Match[str]) -> str:
            if tomllib.loads(match[0])["package"][0].get("name") == "mealie-enricher":
                return replace_version_line(match[0], version)
            return match[0]

        contents["uv.lock"] = package_pattern.sub(replace_package, contents["uv.lock"])
        arg_pattern = re.compile(r"(?m)^(ARG VERSION=)([^\r\n]+)(\r?)$")
        matches = list(arg_pattern.finditer(contents["Dockerfile"]))
        if len(matches) != 1:
            raise ValueError("expected one ARG VERSION= assignment")
        version_tuple(matches[0][2])
        contents["Dockerfile"] = arg_pattern.sub(
            lambda match: f"{match[1]}{version}{match[3]}", contents["Dockerfile"]
        )
    except (KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseError(f"Malformed release metadata: {exc}") from exc
    return contents


def expected_commit(source: str, version: str, contents: dict[str, str]) -> str:
    """Build the release tree without touching the working tree or its index."""
    with tempfile.TemporaryDirectory(
        prefix="mealie-release-", dir=git("rev-parse", "--git-dir")
    ) as temporary:
        index_env = {"GIT_INDEX_FILE": str(Path(temporary) / "index")}
        git("read-tree", source, env=index_env)
        for name, content in contents.items():
            mode = git("ls-files", "--stage", "--", name).split()[0]
            blob = git("hash-object", "-w", f"--path={name}", "--stdin", input_text=content)
            git("update-index", "--add", "--cacheinfo", f"{mode},{blob},{name}", env=index_env)
        tree = git("write-tree", env=index_env)
    if tree == git("rev-parse", f"{source}^{{tree}}"):
        return source
    date = git("show", "-s", "--format=%cI", source)
    return git(
        "-c",
        "commit.gpgsign=false",
        "commit-tree",
        tree,
        "-p",
        source,
        input_text=release_message(version, source) + "\n",
        env={
            "GIT_AUTHOR_NAME": BOT_NAME,
            "GIT_AUTHOR_EMAIL": BOT_EMAIL,
            "GIT_COMMITTER_NAME": BOT_NAME,
            "GIT_COMMITTER_EMAIL": BOT_EMAIL,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
        },
    )


def validate_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ReleaseError("Release plan must be a JSON object")
    if not isinstance(plan.get("version"), str):
        raise ReleaseError("Release plan has no valid version")
    version_tuple(plan["version"])
    if plan.get("tag") != f"v{plan['version']}":
        raise ReleaseError("Release plan tag does not match its version")
    for key in ("source_sha", "release_sha"):
        if not isinstance(plan.get(key), str) or not SHA_RE.fullmatch(plan[key]):
            raise ReleaseError(f"Release plan has invalid {key}")
    if type(plan.get("resumed")) is not bool:
        raise ReleaseError("Release plan has invalid resumed flag")
    if "superseded" in plan and type(plan["superseded"]) is not bool:
        raise ReleaseError("Release plan has invalid superseded flag")
    expected = {"version", "source_sha", "release_sha", "tag", "resumed", "superseded"}
    if set(plan) - expected:
        raise ReleaseError("Release plan contains unexpected fields")
    return plan


def github_output(plan: dict[str, Any], path: str | None) -> None:
    validate_plan(plan)
    if path:
        with Path(path).open("a", encoding="utf-8", newline="\n") as output:
            for key, value in plan.items():
                output.write(f"{key}={str(value).lower() if type(value) is bool else value}\n")


def prepare(output: str) -> dict[str, Any]:
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ReleaseError("Refusing to prepare a release from a dirty worktree")
    source = git("rev-parse", "HEAD")
    tags = own_tags()
    version, resumed = select_version(source, tags)
    contents = version_contents(version)
    release = expected_commit(source, version, contents)
    tag = f"v{version}"
    if tag in tags and tags[tag] != release:
        raise ReleaseError(f"Conflicting release tag {tag} points to a different commit or tree")
    if release != source:
        git("update-ref", "HEAD", release, source)
        git("read-tree", "--reset", "-u", release)
    if tag not in tags:
        git("-c", "tag.gpgsign=false", "tag", tag, release)
    plan = validate_plan(
        {
            "version": version,
            "source_sha": source,
            "release_sha": release,
            "tag": tag,
            "resumed": resumed,
        }
    )
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def push(path: str) -> dict[str, Any]:
    plan = validate_plan(json.loads(Path(path).read_text(encoding="utf-8")))
    if git("rev-parse", "HEAD") != plan["release_sha"]:
        raise ReleaseError("HEAD does not match the prepared release")
    if git("rev-parse", f"refs/tags/{plan['tag']}^{{commit}}") != plan["release_sha"]:
        raise ReleaseError("Local tag does not match the prepared release")
    remote = git("ls-remote", "origin", "refs/heads/main")
    remote_sha = remote.split()[0] if remote else None
    plan["superseded"] = remote_sha not in (plan["source_sha"], plan["release_sha"])
    if not plan["superseded"]:
        git("push", "--atomic", "origin", "HEAD:refs/heads/main", f"refs/tags/{plan['tag']}")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--output", required=True)
    preparation.add_argument("--github-output")
    publication = commands.add_parser("push")
    publication.add_argument("--plan", required=True)
    publication.add_argument("--github-output")
    args = parser.parse_args()
    try:
        root = git("rev-parse", "--show-toplevel")
        os.chdir(root)
        plan = prepare(args.output) if args.command == "prepare" else push(args.plan)
        github_output(plan, args.github_output)
        print(json.dumps(plan))
        return 0
    except (ReleaseError, OSError, ValueError) as exc:
        print(f"Release error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
