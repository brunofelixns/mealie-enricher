import pytest

from mealie_enricher.models import MealieUnit
from mealie_enricher.services.unit_converter import convert_to_grams
from tests.parity.cases import cases_for


@pytest.mark.parametrize("case", cases_for("conversion"), ids=lambda case: case["id"])
def test_unit_conversion_matches_reference(case):
    data = case["input"]
    assert (
        convert_to_grams(data["quantity"], MealieUnit.model_validate(data["unit"]))
        == case["expected_result"]
    )
