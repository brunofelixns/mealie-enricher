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


def test_registry_auth_failure_is_not_treated_as_a_missing_image():
    from ci.images import registry_digest

    def denied(args, check=True):
        return subprocess.CompletedProcess(args, 1, "", "unauthorized: access denied")

    with pytest.raises(RuntimeError, match="unauthorized"):
        registry_digest("ghcr.io/example/app:1.0.0", call=denied)
