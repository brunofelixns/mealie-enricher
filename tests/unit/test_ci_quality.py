"""Release metadata and coverage gates reject misleading inputs."""

import pytest

from ci.quality import check_coverage, check_title


@pytest.mark.parametrize(
    "title",
    [
        "feat: add catalog",
        "fix(api)!: change response",
        "chore(main): release 1.0.1",
        "docs: añade ejemplos",
    ],
)
def test_conventional_pr_titles(title):
    check_title(title)


@pytest.mark.parametrize(
    "title",
    [
        "Add catalog",
        "feat: ",
        "feat(): add",
        "fix: Add catalog",
        "fix: add catalog.",
        "fix: add\nops: injected",
        "unknown: add",
    ],
)
def test_invalid_pr_titles(title):
    with pytest.raises(ValueError):
        check_title(title)


@pytest.mark.parametrize("covered,valid,expected", [(95, 100, 95), (100, 100, 100)])
def test_coverage_threshold_boundary(tmp_path, covered, valid, expected):
    report = tmp_path / "coverage.xml"
    report.write_text(f'<coverage lines-covered="{covered}" lines-valid="{valid}"/>')
    assert check_coverage(report, 95) == expected


@pytest.mark.parametrize(
    "body",
    [
        '<coverage lines-covered="94" lines-valid="100"/>',
        '<coverage lines-covered="0" lines-valid="0"/>',
        '<coverage lines-covered="101" lines-valid="100"/>',
        '<coverage line-rate="1"/>',
        "<broken",
    ],
)
def test_inadequate_or_invalid_coverage_blocks_ci(tmp_path, body):
    report = tmp_path / "coverage.xml"
    report.write_text(body)
    with pytest.raises(ValueError):
        check_coverage(report, 95)
