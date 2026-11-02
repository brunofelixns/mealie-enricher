"""Exercise actual Linux bind-mount permissions using the production container options."""

import os
import subprocess

import pytest

from ci.security import container_command, scanner_image


@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SMOKE") != "1",
    reason="Set RUN_DOCKER_SMOKE=1 for Docker permissions check",
)
def test_scanner_writes_runner_owned_reports_and_cache(tmp_path):
    reports, cache = tmp_path / "reports", tmp_path / "cache"
    reports.mkdir()
    cache.mkdir()
    command = container_command(reports, cache)
    image_position = command.index(scanner_image())
    command = [
        *command[:image_position],
        "--entrypoint",
        "/bin/sh",
        scanner_image(),
        "-c",
        "touch /reports/probe /cache/trivy/probe",
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stderr
    assert (reports / "probe").exists() and (cache / "probe").exists()
