import pytest

from mealie_enricher.compat import js_number_str, js_round
from mealie_enricher.models import MealieRecipe
from mealie_enricher.services.estimator import compute_ingredient_hash
from tests.parity.cases import cases_for


@pytest.mark.parametrize("case", cases_for("hash"), ids=lambda case: case["id"])
def test_ingredient_hash_matches_reference(case):
    assert (
        compute_ingredient_hash(MealieRecipe.model_validate(case["input"]))
        == case["expected_result"]
    )


@pytest.mark.parametrize(
    "value,expected", [(0.5, 1), (-0.5, 0), (-1.5, -1), (0.49999999999999994, 0)]
)
def test_rounding_keeps_javascript_ties(value, expected):
    assert js_round(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(1.0, "1"), (-0.0, "0"), (1e-7, "1e-7"), (1e-6, "0.000001"), (1e20, "100000000000000000000")],
)
def test_numeric_hash_text_uses_javascript_not_python_repr(value, expected):
    assert js_number_str(value) == expected
