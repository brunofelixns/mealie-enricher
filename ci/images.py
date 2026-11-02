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


def publication_images(data):
    """Read current single-image manifests and immutable historical releases."""
    if "image_digest" in data:
        if "base_digest" in data or "bedca_digest" in data:
            raise ValueError("Manifiesto de publicación ambiguo")
        images = {"image": data["image_digest"]}
    else:
        images = {name: data.get(f"{name}_digest") for name in ("base", "bedca")}
    if any(
        not isinstance(digest, str) or not DIGEST.fullmatch(digest) for digest in images.values()
    ):
        raise ValueError("Digest de publicación inválido")
    return images


def validate_manifest(data):
    if not REPOSITORY.fullmatch(data["repository"]) or not VERSION.fullmatch(data["version"]):
        raise ValueError("Repositorio o versión de publicación inválidos")
    publication_images(data)


def promote(data, *, call=run, publish_aliases=True):
    validate_manifest(data)
    repository, version = data["repository"], data["version"]
    complete = "image_digest" in data
    digest = data["image_digest"] if complete else data["base_digest"]
    catalog_digest = digest if complete else data["bedca_digest"]
    targets = [(f"{repository}:{version}", digest)]
    if not complete:
        targets.append((f"{repository}:{version}-bedca", catalog_digest))
    # Check all immutable version tags before writing any stable alias.
    for tag, expected_digest in targets:
        existing = registry_digest(tag, call=call)
        if existing is not None and existing != expected_digest:
            raise ValueError(f"La versión inmutable ya existe con otro contenido: {tag}")
    if publish_aliases:
        targets.extend(
            [
                (f"{repository}:latest", digest),
                (f"{repository}:bedca", catalog_digest),
                (f"{repository}:latest-bedca", catalog_digest),
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
if sys.argv[3] in ('bedca','image'):
 from mealie_enricher.catalog.store import DuckDbCatalog
 root=pathlib.Path('/opt/bedca')
 assert len(list((root/'source').glob('*.csv')))==3
 catalog=DuckDbCatalog(str(root/'catalogos.duckdb'))
 assert catalog.inspect()['food_count']==957
 catalog.close()
 if sys.argv[3]=='image':
  assert os.environ['CATALOG_ENABLED']=='true'
  assert os.environ['CATALOG_DB_PATH']=='/opt/bedca/catalogos.duckdb'
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
    tag = f"{repository}:build-{revision}"
    digest = registry_digest(tag)
    if digest is None:
        metadata = Path(".cache/image-build-metadata.json")
        run(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                "linux/amd64,linux/arm64",
                "--provenance=false",
                "--sbom=false",
                "--metadata-file",
                str(metadata),
                "--build-context",
                "bedca_source=./data/bedca",
                "--build-arg",
                "BEDCA_DATASET_VERSION=bedca-export-2026-08-19",
                "--build-arg",
                f"VERSION={version}",
                "--build-arg",
                f"VCS_REF={revision}",
                "--tag",
                tag,
                "--push",
                ".",
            ]
        )
        digest = json.loads(metadata.read_text(encoding="utf-8"))["containerimage.digest"]
        if registry_digest(tag) != digest:
            raise RuntimeError(f"No se verificó el candidato: {tag}")
    data["image_digest"] = digest
    smoke(f"{repository}@{digest}", version, revision, "image")
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
    promoter.add_argument("--version-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "build":
            build(args.repository, args.version, args.revision, args.output)
        else:
            promote(
                json.loads(args.manifest.read_text(encoding="utf-8")),
                publish_aliases=not args.version_only,
            )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
