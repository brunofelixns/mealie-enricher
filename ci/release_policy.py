"""Read-only version policy and validation for Release Please and GHCR."""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
LEGACY = "1.13.0"


def version_tuple(value):
    if not isinstance(value, str) or not SEMVER.fullmatch(value):
        raise ValueError("Versión estable inválida")
    return tuple(map(int, value.split(".")))


def tag_version(tag):
    if not tag.startswith("v"):
        raise ValueError("Tag de publicación inválido")
    value = tag[1:]
    if version_tuple(value) < (1, 0, 0) or value == LEGACY:
        raise ValueError("Tag histórico o inválido")
    return value


def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, encoding="utf-8")
    if result.returncode:
        raise ValueError(f"Git: {result.stderr.strip()}")
    return result.stdout.strip()


def plan(source=None):
    source = git("rev-parse", (source or "HEAD") + "^{commit}")
    tags = {}
    for tag in git("tag", "--merged", source).splitlines():
        try:
            tags[tag_version(tag)] = tag
        except ValueError:
            continue
    if not tags:
        return {"next_version": "1.0.0"}
    previous = max(tags, key=version_tuple)
    if git("rev-parse", tags[previous] + "^{commit}") == source:
        return {"next_version": previous}
    messages = git("log", "--format=%B%x00", f"{tags[previous]}..{source}")
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
    major, minor, patch = version_tuple(previous)
    candidate = (
        f"{major + 1}.0.0"
        if bump == 2
        else f"{major}.{minor + 1}.0"
        if bump == 1
        else f"{major}.{minor}.{patch + 1}"
    )
    return {"next_version": "1.13.1" if candidate == LEGACY else candidate}


def metadata_version(read_content=None):
    read = read_content or (lambda name: Path(name).read_text(encoding="utf-8"))
    project = tomllib.loads(read("pyproject.toml"))["project"]
    lock = tomllib.loads(read("uv.lock"))
    packages = [p for p in lock["package"] if p["name"] == "mealie-enricher"]
    docker = re.findall(r"(?m)^ARG VERSION=([^\r\n]+)$", read("Dockerfile"))
    manifest = json.loads(read(".release-please-manifest.json"))
    if project["name"] != "mealie-enricher" or len(packages) != 1 or len(docker) != 1:
        raise ValueError("Los metadatos de versión están incompletos")
    version = project["version"]
    version_tuple(version)
    if any(v != version for v in (packages[0]["version"], docker[0], manifest["."])):
        raise ValueError("Los metadatos de versión no coinciden")
    return version


def resolve(tag):
    version = tag_version(tag)
    source = git("rev-parse", f"refs/tags/{tag}^{{commit}}")
    try:
        git("merge-base", "--is-ancestor", source, "refs/remotes/origin/main")
    except ValueError as error:
        raise ValueError("El commit publicado debe pertenecer a main") from error
    if metadata_version(lambda name: git("show", f"{source}:{name}")) != version:
        raise ValueError("Los metadatos no coinciden con el tag")
    return {"version": version, "sha": source, "tag": tag}


def verify(tag):
    result = resolve(tag)
    if git("rev-parse", "HEAD") != result["sha"]:
        raise ValueError("El commit probado no coincide con el tag")
    if metadata_version() != result["version"]:
        raise ValueError("Los metadatos no coinciden con el tag")
    return result


def aliases(version, releases):
    versions = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        try:
            versions.append(tag_version(release["tag_name"]))
        except ValueError:
            continue
    if version not in versions:
        raise ValueError("La versión no tiene una release estable publicada")
    return {"publish_aliases": version == max(versions, key=version_tuple)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["plan", "resolve", "verify", "metadata", "aliases", "proposal"]
    )
    parser.add_argument("--base")
    parser.add_argument("--tag")
    parser.add_argument("--version")
    parser.add_argument("--releases", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan()
        elif args.command == "verify":
            result = verify(args.tag or "")
        elif args.command == "resolve":
            result = resolve(args.tag or "")
        elif args.command == "metadata":
            result = {"version": metadata_version()}
        elif args.command == "proposal":
            if not args.base or not re.fullmatch(r"[0-9a-f]{40}", args.base):
                raise ValueError("Commit base inválido")
            expected = plan(args.base)["next_version"]
            if metadata_version() != expected:
                raise ValueError(f"La versión propuesta debe ser {expected} para esta base")
            result = {"version": expected}
        else:
            result = aliases(args.version, json.loads(args.releases.read_text(encoding="utf-8")))
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
                for key, value in result.items():
                    output.write(
                        f"{key}={str(value).lower() if isinstance(value, bool) else value}\n"
                    )
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
