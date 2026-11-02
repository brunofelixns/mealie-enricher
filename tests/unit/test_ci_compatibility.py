"""Scheduled compatibility must exercise the selected Mealie image."""

from tests.support.mealie_stack import MealieStack


def test_default_image_is_owned_by_compose_not_the_fixture(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_MEALIE_IMAGE", raising=False)
    stack = MealieStack(tmp_path)
    try:
        assert "TEST_MEALIE_IMAGE" not in stack.values
    finally:
        stack.mealie.close()
        stack.app.close()


def test_isolated_stack_propagates_explicit_mealie_image(tmp_path, monkeypatch):
    image = "ghcr.io/mealie-recipes/mealie:v3.19.2@sha256:" + "a" * 64
    monkeypatch.setenv("TEST_MEALIE_IMAGE", image)
    stack = MealieStack(tmp_path)
    try:
        assert stack.values["TEST_MEALIE_IMAGE"] == image
        stack.save_env()
        assert f"TEST_MEALIE_IMAGE={image}" in (tmp_path / "test.env").read_text()
    finally:
        stack.mealie.close()
        stack.app.close()
