"""Scan exact platform manifests and preserve release evidence before promotion."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci.images import DIGEST, REPOSITORY, registry_digest, run

REPOSITORY_NAME = "ghcr.io/brunofelixns/mealie-enricher"


def platform_digests(index):
    platforms = {}
    for architecture in ("amd64", "arm64"):
        matches = [
            item.get("digest", "")
            for item in index.get("manifests", [])
            if item.get("platform", {}).get("os") == "linux"
            and item.get("platform", {}).get("architecture") == architecture
        ]
        if len(matches) != 1 or not DIGEST.fullmatch(matches[0]):
            raise ValueError(f"Falta un manifiesto único linux/{architecture}")
        platforms[architecture] = matches[0]
    return platforms


def blocking_findings(report, reference):
    if report.get("SchemaVersion") != 2 or report.get("ArtifactName") != reference:
        raise ValueError("Informe Trivy vacío, incompatible o de otra imagen")
    results = report.get("Results")
    if (
        not isinstance(results, list)
        or not results
        or not any(
            isinstance(item, dict) and item.get("Class") == "os-pkgs" and item.get("Packages")
            for item in results
        )
    ):
        raise ValueError("Trivy no ha inventariado los paquetes del sistema")
    blocking = []
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Resultado Trivy inválido")
        vulnerabilities = result.get("Vulnerabilities")
        if vulnerabilities is None:
            vulnerabilities = []
        if not isinstance(vulnerabilities, list):
            raise ValueError("Lista de vulnerabilidades inválida")
        for finding in vulnerabilities:
            if (
                not isinstance(finding, dict)
                or not all(
                    isinstance(finding.get(key), str) and finding[key]
                    for key in ("VulnerabilityID", "PkgName", "InstalledVersion", "Severity")
                )
                or finding["Severity"] not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
            ):
                raise ValueError("Vulnerabilidad incompleta")
            if (
                finding["Severity"] in {"HIGH", "CRITICAL"}
                and finding.get("FixedVersion", "").strip()
            ):
                blocking.append(finding)
    return blocking


def validate_sbom(data):
    if (
        data.get("bomFormat") != "CycloneDX"
        or not data.get("specVersion")
        or not isinstance(data.get("components"), list)
        or not data["components"]
        or not all(isinstance(item, dict) and item.get("name") for item in data["components"])
    ):
        raise ValueError("SBOM CycloneDX vacío o inválido")


def scanner_image():
    definition = Path(__file__).with_name("trivy") / "Dockerfile"
    image = next(
        line.removeprefix("FROM ")
        for line in definition.read_text().splitlines()
        if line.startswith("FROM ")
    )
    if not re.fullmatch(r"ghcr\.io/aquasecurity/trivy:[0-9.]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("El escáner debe estar fijado por versión y digest")
    return image


def container_command(destination, cache):
    uid = getattr(os, "getuid", lambda: 0)()
    gid = getattr(os, "getgid", lambda: 0)()
    return [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{uid}:{gid}",
        "--env",
        "HOME=/tmp",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=2g",
        "--mount",
        f"type=bind,source={destination.resolve()},target=/reports",
        "--mount",
        f"type=bind,source={cache.resolve()},target=/cache/trivy",
        scanner_image(),
        "--cache-dir",
        "/cache/trivy",
    ]


def scan(manifest, destination):
    repository = manifest["repository"]
    if not REPOSITORY.fullmatch(repository):
        raise ValueError("Repositorio de escaneo inválido")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "security-summary.json").unlink(missing_ok=True)
    cache = destination.parent / "trivy-cache"
    cache.mkdir(exist_ok=True)
    scanner = scanner_image()
    artifacts = []
    for variant in ("base", "bedca"):
        digest = manifest[f"{variant}_digest"]
        if not DIGEST.fullmatch(digest):
            raise ValueError("Digest de escaneo inválido")
        index_reference = f"{repository}@{digest}"
        index = json.loads(
            run(["docker", "buildx", "imagetools", "inspect", index_reference, "--raw"]).stdout
        )
        for architecture, child in platform_digests(index).items():
            name = f"{variant}-{architecture}"
            reference = f"{repository}@{child}"
            command = container_command(destination, cache)
            scan_command = [
                *command,
                "image",
                "--no-progress",
                "--image-src",
                "remote",
                "--platform",
                f"linux/{architecture}",
            ]
            run(
                [
                    *scan_command,
                    "--scanners",
                    "vuln",
                    "--list-all-pkgs",
                    "--format",
                    "json",
                    "--output",
                    f"/reports/{name}.trivy.json",
                    reference,
                ]
            )
            report = json.loads((destination / f"{name}.trivy.json").read_text(encoding="utf-8"))
            blocking = blocking_findings(report, reference)
            run(
                [
                    *command,
                    "convert",
                    "--format",
                    "cyclonedx",
                    "--output",
                    f"/reports/{name}.cdx.json",
                    f"/reports/{name}.trivy.json",
                ]
            )
            validate_sbom(
                json.loads((destination / f"{name}.cdx.json").read_text(encoding="utf-8"))
            )
            policy_report = {
                **report,
                "Results": [
                    {
                        **result,
                        "Vulnerabilities": [
                            finding
                            for finding in result.get("Vulnerabilities") or []
                            if finding in blocking
                        ],
                    }
                    for result in report["Results"]
                ],
            }
            (destination / f"{name}.policy.json").write_text(
                json.dumps(policy_report), encoding="utf-8"
            )
            run(
                [
                    *command,
                    "convert",
                    "--format",
                    "sarif",
                    "--output",
                    f"/reports/{name}.sarif",
                    f"/reports/{name}.policy.json",
                ]
            )
            artifacts.append(
                {
                    "name": name,
                    "variant": variant,
                    "architecture": architecture,
                    "index_digest": digest,
                    "digest": child,
                    "reference": reference,
                    "blocking": blocking,
                }
            )
    summary = {
        "scanner": scanner,
        "repository": repository,
        "artifacts": artifacts,
        "passed": not any(item["blocking"] for item in artifacts),
    }
    (destination / "security-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    text = (
        "### Seguridad de imágenes\n\n"
        + "\n".join(
            f"- {item['name']}: {len(item['blocking'])} vulnerabilidades HIGH/CRITICAL con corrección disponible."
            for item in artifacts
        )
        + "\n"
    )
    print(text)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as output:
            output.write(text)
    if not summary["passed"]:
        raise ValueError(
            "La política de seguridad bloquea estas imágenes; consultar los informes completos"
        )
    if path := os.environ.get("GITHUB_OUTPUT"):
        with Path(path).open("a", encoding="utf-8") as output:
            for variant in ("base", "bedca"):
                output.write(f"{variant}_digest={manifest[f'{variant}_digest']}\n")
            for item in artifacts:
                output.write(f"{item['name'].replace('-', '_')}_digest={item['digest']}\n")
    return summary


def write_provenance(manifest, destination):
    from ci.images import validate_manifest

    validate_manifest(manifest)
    revision = manifest["revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Revisión de procedencia inválida")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repository = os.environ.get("GITHUB_REPOSITORY", "brunofelixns/mealie-enricher")
    invocation = f"{server}/{repository}/actions/runs/{os.environ.get('GITHUB_RUN_ID', 'local')}/attempts/{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    for variant in ("base", "bedca"):
        predicate = {
            "buildDefinition": {
                "buildType": "https://github.com/brunofelixns/mealie-enricher/ci/verified-promotion/v1",
                "externalParameters": {"releaseTag": f"v{manifest['version']}", "variant": variant},
                "internalParameters": {"candidateDigest": manifest[f"{variant}_digest"]},
                "resolvedDependencies": [
                    {"uri": f"git+{server}/{repository}", "digest": {"gitCommit": revision}}
                ],
            },
            "runDetails": {
                "builder": {
                    "id": f"{server}/{repository}/.github/workflows/ci-release.yml@refs/heads/main"
                },
                "metadata": {"invocationId": invocation},
            },
        }
        (destination / f"{variant}.provenance.json").write_text(
            json.dumps(predicate, indent=2) + "\n", encoding="utf-8"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--published", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.published == bool(args.manifest):
            raise ValueError("Elige --manifest o --published")
        if args.published:
            manifest = {
                "repository": REPOSITORY_NAME,
                "base_digest": registry_digest(f"{REPOSITORY_NAME}:latest"),
                "bedca_digest": registry_digest(f"{REPOSITORY_NAME}:bedca"),
            }
            if not manifest["base_digest"] or not manifest["bedca_digest"]:
                raise ValueError("Faltan imágenes publicadas")
        else:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        scan(manifest, args.output)
        if not args.published:
            write_provenance(manifest, args.output)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
