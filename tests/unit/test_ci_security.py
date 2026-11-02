"""Image evidence must cover the exact digest and all required platforms."""

import copy
import json
import subprocess

import pytest

from ci.security import blocking_findings, platform_digests, validate_sbom

REFERENCE = "ghcr.io/example/app@sha256:" + "a" * 64


def report():
    return {
        "SchemaVersion": 2,
        "ArtifactName": REFERENCE,
        "Results": [
            {
                "Class": "os-pkgs",
                "Type": "debian",
                "Target": "Debian",
                "Packages": [{"Name": "libc6"}],
                "Vulnerabilities": [],
            }
        ],
    }


def test_clean_scan_is_accepted():
    assert blocking_findings(report(), REFERENCE) == []


def test_only_fixable_high_or_critical_findings_block():
    data = report()
    data["Results"][0]["Vulnerabilities"] = [
        {
            "VulnerabilityID": "CVE-1",
            "PkgName": "pkg",
            "InstalledVersion": "1",
            "Severity": "HIGH",
            "FixedVersion": "2",
        },
        {
            "VulnerabilityID": "CVE-2",
            "PkgName": "pkg",
            "InstalledVersion": "1",
            "Severity": "CRITICAL",
        },
        {
            "VulnerabilityID": "CVE-3",
            "PkgName": "pkg",
            "InstalledVersion": "1",
            "Severity": "LOW",
            "FixedVersion": "2",
        },
    ]
    assert [item["VulnerabilityID"] for item in blocking_findings(data, REFERENCE)] == ["CVE-1"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.clear(),
        lambda data: data.update(Results=[]),
        lambda data: data.update(ArtifactName="different"),
        lambda data: data["Results"][0].pop("Packages"),
        lambda data: data["Results"][0].update(Vulnerabilities=[{}]),
        lambda data: data["Results"][0].update(Vulnerabilities={}),
    ],
)
def test_incomplete_scans_fail_closed(mutation):
    data = copy.deepcopy(report())
    mutation(data)
    with pytest.raises(ValueError):
        blocking_findings(data, REFERENCE)


def test_platform_selection_ignores_attestation_manifests():
    index = {
        "manifests": [
            {"digest": "sha256:" + "a" * 64, "platform": {"os": "linux", "architecture": "amd64"}},
            {"digest": "sha256:" + "b" * 64, "platform": {"os": "linux", "architecture": "arm64"}},
            {
                "digest": "sha256:" + "c" * 64,
                "platform": {"os": "unknown", "architecture": "unknown"},
            },
        ]
    }
    assert set(platform_digests(index)) == {"amd64", "arm64"}
    index["manifests"].pop(1)
    with pytest.raises(ValueError, match="arm64"):
        platform_digests(index)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []},
        {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": "not an inventory"},
    ],
)
def test_empty_sbom_is_rejected(data):
    with pytest.raises(ValueError):
        validate_sbom(data)


def fake_scanner(monkeypatch, destination, *, vulnerable=False, broken=False):
    from ci import security

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(destination / "test-summary.md"))
    references = []

    def execute(args, check=True):
        if args[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            result = {
                "manifests": [
                    {
                        "digest": "sha256:" + char * 64,
                        "platform": {"os": "linux", "architecture": architecture},
                    }
                    for architecture, char in (("amd64", "a"), ("arm64", "b"))
                ]
            }
            return subprocess.CompletedProcess(args, 0, json.dumps(result), "")
        assert "docker.sock" not in " ".join(args)
        assert security.scanner_image() in args
        name = args[args.index("--output") + 1].removeprefix("/reports/")
        if "convert" in args:
            data = (
                {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [{"name": "libc6"}]}
                if name.endswith("cdx.json")
                else {"version": "2.1.0", "runs": []}
            )
        else:
            assert "--image-src" in args and args[args.index("--image-src") + 1] == "remote"
            references.append(args[-1])
            if broken:
                raise RuntimeError("Registry unavailable")
            data = report()
            data["ArtifactName"] = args[-1]
            if vulnerable:
                data["Results"][0]["Vulnerabilities"] = [
                    {
                        "VulnerabilityID": "CVE-new",
                        "PkgName": "libc6",
                        "InstalledVersion": "1",
                        "Severity": "HIGH",
                        "FixedVersion": "2",
                    }
                ]
        (destination / name).write_text(json.dumps(data), encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(security, "run", execute)
    return references


@pytest.mark.parametrize("vulnerable", [False, True])
def test_scan_covers_both_platforms_and_variants_before_deciding_policy(
    tmp_path, monkeypatch, vulnerable
):
    from ci.security import scan

    references = fake_scanner(monkeypatch, tmp_path, vulnerable=vulnerable)
    outputs = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    manifest = {
        "repository": "ghcr.io/example/app",
        "base_digest": "sha256:" + "c" * 64,
        "bedca_digest": "sha256:" + "d" * 64,
    }
    if vulnerable:
        with pytest.raises(ValueError, match="bloquea"):
            scan(manifest, tmp_path)
        assert not outputs.exists()
    else:
        scan(manifest, tmp_path)
        assert "base_arm64_digest=sha256:" + "b" * 64 in outputs.read_text()
    evidence = json.loads((tmp_path / "security-summary.json").read_text())
    assert len(references) == len(evidence["artifacts"]) == 4
    assert evidence["passed"] is not vulnerable
    assert all((tmp_path / (item["name"] + ".cdx.json")).exists() for item in evidence["artifacts"])


def test_failed_retry_cannot_leave_a_stale_success_receipt(tmp_path, monkeypatch):
    from ci.security import scan

    fake_scanner(monkeypatch, tmp_path, broken=True)
    receipt = tmp_path / "security-summary.json"
    receipt.write_text('{"passed": true}')
    with pytest.raises(RuntimeError, match="Registry unavailable"):
        scan({"repository": "ghcr.io/example/app", "base_digest": "sha256:" + "c" * 64}, tmp_path)
    assert not receipt.exists()


def test_provenance_binds_release_checkout_rather_than_workflow_main_sha(tmp_path, monkeypatch):
    from ci.security import write_provenance

    monkeypatch.setenv("GITHUB_SHA", "c" * 40)
    manifest = {
        "repository": "ghcr.io/example/app",
        "version": "1.0.1",
        "revision": "d" * 40,
        "base_digest": "sha256:" + "a" * 64,
        "bedca_digest": "sha256:" + "b" * 64,
    }
    write_provenance(manifest, tmp_path)
    for variant in ("base", "bedca"):
        predicate = json.loads((tmp_path / f"{variant}.provenance.json").read_text())
        definition = predicate["buildDefinition"]
        assert definition["resolvedDependencies"][0]["digest"] == {"gitCommit": "d" * 40}
        assert definition["internalParameters"]["candidateDigest"] == manifest[f"{variant}_digest"]
