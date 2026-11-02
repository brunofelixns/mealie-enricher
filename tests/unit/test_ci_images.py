import json
import subprocess

import pytest


class Registry:
    def __init__(self, images):
        self.images = dict(images)
        self.writes = []

    def __call__(self, args, check=True):
        if args[:3] == ["docker", "buildx", "imagetools"]:
            if args[3] == "inspect":
                value = self.images.get(args[4])
                return subprocess.CompletedProcess(
                    args,
                    0 if value else 1,
                    json.dumps({"digest": value}) if value else "",
                    "not found" if not value else "",
                )
            assert args[3] == "create"
            digest = args[-1].split("@", 1)[1]
            for index, arg in enumerate(args):
                if arg == "--tag":
                    self.images[args[index + 1]] = digest
                    self.writes.append(args[index + 1])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)


def manifest():
    return {
        "repository": "ghcr.io/example/app",
        "version": "1.0.0",
        "base_digest": "sha256:" + "a" * 64,
        "bedca_digest": "sha256:" + "b" * 64,
    }


def complete_manifest():
    return {
        "repository": "ghcr.io/example/app",
        "version": "1.2.0",
        "revision": "d" * 40,
        "image_digest": "sha256:" + "c" * 64,
    }


def test_complete_image_publishes_one_version_and_shared_compatibility_aliases():
    from ci.images import promote

    data = complete_manifest()
    registry = Registry({})
    promote(data, call=registry)
    assert registry.images == {
        f"ghcr.io/example/app:{tag}": data["image_digest"]
        for tag in ("1.2.0", "latest", "bedca", "latest-bedca")
    }


def test_complete_image_conflict_blocks_every_alias_write():
    from ci.images import promote

    registry = Registry({"ghcr.io/example/app:1.2.0": "sha256:" + "e" * 64})
    with pytest.raises(ValueError, match="inmutable"):
        promote(complete_manifest(), call=registry)
    assert registry.writes == []


def test_complete_image_can_repair_version_without_moving_newer_aliases():
    from ci.images import promote

    current = "sha256:" + "e" * 64
    registry = Registry({"ghcr.io/example/app:latest": current})
    promote(complete_manifest(), call=registry, publish_aliases=False)
    assert registry.writes == ["ghcr.io/example/app:1.2.0"]
    assert registry.images["ghcr.io/example/app:latest"] == current


@pytest.mark.parametrize(
    "changes",
    [
        {"image_digest": "not-a-digest"},
        {"base_digest": "sha256:" + "a" * 64},
        {"bedca_digest": "sha256:" + "b" * 64},
    ],
)
def test_complete_image_rejects_invalid_or_mixed_manifests_before_writes(changes):
    from ci.images import promote

    registry = Registry({})
    with pytest.raises(ValueError):
        promote({**complete_manifest(), **changes}, call=registry)
    assert registry.writes == []


@pytest.mark.parametrize("already_built", [False, True])
def test_build_pushes_only_one_complete_candidate_and_reuses_it_on_retry(
    monkeypatch, tmp_path, already_built
):
    from ci import images

    monkeypatch.chdir(tmp_path)
    data = complete_manifest()
    candidate = "ghcr.io/example/app:build-" + data["revision"]
    existing = {candidate: data["image_digest"]} if already_built else {}
    builds, probes = [], []

    def docker(args, check=True):
        assert args[:3] == ["docker", "buildx", "build"]
        builds.append(args)
        metadata = tmp_path / args[args.index("--metadata-file") + 1]
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(json.dumps({"containerimage.digest": data["image_digest"]}))
        existing[candidate] = data["image_digest"]
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(images, "registry_digest", existing.get)
    monkeypatch.setattr(images, "run", docker)
    monkeypatch.setattr(images, "smoke", lambda *args: probes.append(args))
    output = tmp_path / "release-images.json"
    images.build(data["repository"], data["version"], data["revision"], output)
    assert json.loads(output.read_text()) == data
    assert len(builds) == (0 if already_built else 1)
    if builds:
        command = builds[0]
        assert "--push" in command
        assert command[command.index("--platform") + 1] == "linux/amd64,linux/arm64"
        assert command[command.index("--build-context") + 1] == "bedca_source=./data/bedca"
        assert "BASE_IMAGE=" not in " ".join(command)
    assert probes == [
        (data["repository"] + "@" + data["image_digest"], "1.2.0", data["revision"], "image")
    ]


def test_promotion_updates_both_variants_after_immutable_tags_are_checked():
    from ci.images import promote

    data = manifest()
    registry = Registry({})
    promote(data, call=registry)
    assert registry.images["ghcr.io/example/app:latest"] == data["base_digest"]
    assert registry.images["ghcr.io/example/app:bedca"] == data["bedca_digest"]
    assert registry.images["ghcr.io/example/app:1.0.0-bedca"] == data["bedca_digest"]


def test_conflicting_version_blocks_all_stable_tag_updates():
    from ci.images import promote

    registry = Registry({"ghcr.io/example/app:1.0.0-bedca": "sha256:" + "c" * 64})
    with pytest.raises(ValueError, match="inmutable"):
        promote(manifest(), call=registry)
    assert registry.writes == []


def test_identical_version_can_repair_a_partial_promotion():
    from ci.images import promote

    data = manifest()
    registry = Registry(
        {
            "ghcr.io/example/app:1.0.0": data["base_digest"],
            "ghcr.io/example/app:1.0.0-bedca": data["bedca_digest"],
        }
    )
    promote(data, call=registry)
    assert registry.images["ghcr.io/example/app:latest-bedca"] == data["bedca_digest"]


def test_old_release_repair_preserves_current_aliases():
    from ci.images import promote

    current = "sha256:" + "e" * 64
    registry = Registry(
        {"ghcr.io/example/app:latest": current, "ghcr.io/example/app:bedca": current}
    )
    promote(manifest(), call=registry, publish_aliases=False)
    assert registry.images["ghcr.io/example/app:latest"] == current
    assert registry.images["ghcr.io/example/app:bedca"] == current
    assert registry.images["ghcr.io/example/app:1.0.0"] == manifest()["base_digest"]


def test_registry_auth_failure_is_not_treated_as_a_missing_image():
    from ci.images import registry_digest

    def denied(args, check=True):
        return subprocess.CompletedProcess(args, 1, "", "unauthorized: access denied")

    with pytest.raises(RuntimeError, match="unauthorized"):
        registry_digest("ghcr.io/example/app:1.0.0", call=denied)


def platform_index():
    return {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:" + digest * 64,
                "size": 1000,
                "platform": {"os": "linux", "architecture": architecture},
            }
            for architecture, digest in (("amd64", "a"), ("arm64", "b"))
        ],
    }


def test_smoke_verifies_both_platforms_with_a_classic_docker_store(monkeypatch):
    from ci import images

    root = "ghcr.io/example/app"
    index_reference = root + "@sha256:" + "c" * 64
    platform_references = {
        root + "@sha256:" + "a" * 64: "linux/amd64",
        root + "@sha256:" + "b" * 64: "linux/arm64",
    }
    loaded = {}
    verified = []

    def docker(args, check=True):
        output = ""
        if args[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            assert args[4:] == [index_reference, "--raw"]
            output = json.dumps(platform_index())
        elif args[:2] == ["docker", "pull"]:
            platform, reference = args[-2:]
            if reference in loaded and loaded[reference] != platform:
                raise RuntimeError("cannot overwrite digest")
            if reference != index_reference:
                assert platform_references[reference] == platform
            loaded[reference] = platform
        elif args[:3] == ["docker", "image", "inspect"]:
            assert args[-1] in loaded
            output = json.dumps(
                [
                    {
                        "Config": {
                            "Labels": {
                                "org.opencontainers.image.version": "1.0.0",
                                "org.opencontainers.image.revision": "d" * 40,
                            }
                        }
                    }
                ]
            )
        else:
            assert args[:2] == ["docker", "run"]
            platform = args[args.index("--platform") + 1]
            reference = args[args.index("python") + 1]
            assert loaded[reference] == platform
            verified.append(platform)
            output = platform
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr(images, "run", docker)
    images.smoke(index_reference, "1.0.0", "d" * 40, "base")
    assert verified == ["linux/amd64", "linux/arm64"]


@pytest.mark.parametrize("invalid", ["missing", "duplicate"])
def test_smoke_rejects_missing_or_ambiguous_platform_before_pull(monkeypatch, invalid):
    from ci import images

    index = platform_index()
    if invalid == "missing":
        index["manifests"].pop()
    else:
        index["manifests"].append(dict(index["manifests"][-1]))

    def docker(args, check=True):
        assert args[:4] == ["docker", "buildx", "imagetools", "inspect"]
        return subprocess.CompletedProcess(args, 0, json.dumps(index), "")

    monkeypatch.setattr(images, "run", docker)
    with pytest.raises(ValueError, match="linux/arm64"):
        images.smoke("ghcr.io/example/app@sha256:" + "c" * 64, "1.0.0", "d" * 40, "base")
