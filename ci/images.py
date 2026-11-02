"""Build verified candidates, then promote immutable releases and stable aliases."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
VERSION = re.compile(r"\d+\.\d+\.\d+")
REPOSITORY = re.compile(r"ghcr\.io/[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*")


def run(args, check=True):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=1800)
    if check and result.returncode:
        raise RuntimeError(
            f"Command failed: {args}\n{result.stdout[-2000:]}\n{result.stderr[-10000:]}"
        )
    return result


def registry_digest(reference, *, call=run):
    result = call(
        ["docker", "buildx", "imagetools", "inspect", reference, "--format", "{{json .Manifest}}"],
        check=False,
    )
    if result.returncode:
        message = result.stderr.lower()
        if "not found" in message or "manifest unknown" in message:
            return None
        raise RuntimeError(result.stderr)
    digest = json.loads(result.stdout)["digest"]
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
        raise ValueError("El registro devolvió un digest inválido")
    return digest


def validate_manifest(data):
    if not REPOSITORY.fullmatch(data["repository"]) or not VERSION.fullmatch(data["version"]):
        raise ValueError("Repositorio o versión de publicación inválidos")
    if any(not DIGEST.fullmatch(data[key]) for key in ("base_digest", "bedca_digest")):
        raise ValueError("Digest de publicación inválido")


def promote(data, *, call=run):
    validate_manifest(data)
    repository, version = data["repository"], data["version"]
    targets = [
        (f"{repository}:{version}", data["base_digest"]),
        (f"{repository}:{version}-bedca", data["bedca_digest"]),
    ]
    # Check both immutable version tags before writing any stable alias.
    for tag, digest in targets:
        existing = registry_digest(tag, call=call)
        if existing is not None and existing != digest:
            raise ValueError(f"La versión inmutable ya existe con otro contenido: {tag}")
    targets.extend(
        [
            (f"{repository}:latest", data["base_digest"]),
            (f"{repository}:bedca", data["bedca_digest"]),
            (f"{repository}:latest-bedca", data["bedca_digest"]),
        ]
    )
    for tag, digest in targets:
        call(["docker", "buildx", "imagetools", "create", "--tag", tag, f"{repository}@{digest}"])
        if registry_digest(tag, call=call) != digest:
            raise RuntimeError(f"No coincide el digest publicado: {tag}")
        print(f"Verified {tag}@{digest}")


PROBE = """
import json,os,pathlib,platform,sys
from importlib.metadata import version
assert version('mealie-enricher')==sys.argv[1]
assert os.getuid()==1000
assert platform.machine() in ({'amd64':{'x86_64'},'arm64':{'aarch64','arm64'}}[sys.argv[2]])
if sys.argv[3]=='bedca':
 from mealie_enricher.catalog.store import DuckDbCatalog
 root=pathlib.Path('/opt/bedca')
 assert len(list((root/'source').glob('*.csv')))==3
 catalog=DuckDbCatalog(str(root/'catalogos.duckdb'))
 assert catalog.inspect()['food_count']==957
 catalog.close()
print(json.dumps({'version':version('mealie-enricher'),'architecture':platform.machine(),'variant':sys.argv[3]}))
"""


def smoke(reference, version, revision, variant):
    index = json.loads(
        run(["docker", "buildx", "imagetools", "inspect", reference, "--raw"]).stdout
    )
    platform_images = {}
    for architecture in ("amd64", "arm64"):
        matches = [
            item["digest"]
            for item in index.get("manifests", [])
            if item.get("platform", {}).get("os") == "linux"
            and item.get("platform", {}).get("architecture") == architecture
        ]
        if len(matches) != 1 or not DIGEST.fullmatch(matches[0]):
            raise ValueError(f"El índice debe identificar una única imagen linux/{architecture}")
        platform_images[architecture] = reference.rsplit("@", 1)[0] + "@" + matches[0]

    for architecture in ("amd64", "arm64"):
        platform = "linux/" + architecture
        # Classic Docker stores cannot bind the same index digest to two platforms.
        platform_reference = platform_images[architecture]
        run(["docker", "pull", "--platform", platform, platform_reference])
        info = json.loads(run(["docker", "image", "inspect", platform_reference]).stdout)[0]
        labels = info["Config"]["Labels"]
        if (
            labels["org.opencontainers.image.version"] != version
            or labels["org.opencontainers.image.revision"] != revision
        ):
            raise ValueError("La imagen no identifica la revisión/versión validada")
        result = run(
            [
                "docker",
                "run",
                "--rm",
                "--platform",
                platform,
                "--network",
                "none",
                "--read-only",
                "--entrypoint",
                "python",
                platform_reference,
                "-c",
                PROBE,
                version,
                architecture,
                variant,
            ]
        )
        print(result.stdout.strip())


def build(repository, version, revision, output):
    if (
        not REPOSITORY.fullmatch(repository)
        or not VERSION.fullmatch(version)
        or not re.fullmatch(r"[0-9a-f]{40}", revision)
    ):
        raise ValueError("Identidad de publicación inválida")
    data = {"repository": repository, "version": version, "revision": revision}
    Path(".cache").mkdir(exist_ok=True)
    for variant in ("base", "bedca"):
        tag = f"{repository}:build-{revision}" + ("-bedca" if variant == "bedca" else "")
        digest = registry_digest(tag)
        if digest is None:
            metadata = Path(f".cache/{variant}-build-metadata.json")
            command = [
                "docker",
                "buildx",
                "build",
                "--platform",
                "linux/amd64,linux/arm64",
                "--provenance=false",
                "--sbom=false",
                "--metadata-file",
                str(metadata),
                "--build-arg",
                f"VERSION={version}",
                "--build-arg",
                f"VCS_REF={revision}",
                "--tag",
                tag,
                "--push",
            ]
            if variant == "bedca":
                command.extend(
                    [
                        "--file",
                        "docker/Dockerfile.bedca",
                        "--build-context",
                        "bedca_source=./data/bedca",
                        "--build-arg",
                        f"BASE_IMAGE={repository}@{data['base_digest']}",
                        "--build-arg",
                        "BEDCA_DATASET_VERSION=bedca-export-2026-08-19",
                        "--network",
                        "none",
                    ]
                )
            run([*command, "."])
            digest = json.loads(metadata.read_text(encoding="utf-8"))["containerimage.digest"]
            if registry_digest(tag) != digest:
                raise RuntimeError(f"No se verificó el candidato: {tag}")
        data[variant + "_digest"] = digest
        smoke(f"{repository}@{digest}", version, revision, variant)
    validate_manifest(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("--repository", required=True)
    builder.add_argument("--version", required=True)
    builder.add_argument("--revision", required=True)
    builder.add_argument("--output", type=Path, required=True)
    promoter = commands.add_parser("promote")
    promoter.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            build(args.repository, args.version, args.revision, args.output)
        else:
            promote(json.loads(args.manifest.read_text(encoding="utf-8")))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
