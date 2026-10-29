import pytest

from mealie_enricher.models import NutrientSet
from mealie_enricher.services.tagging import compute_tags
from tests.parity.cases import cases_for
from tests.parity.spanish import spanish_labels


@pytest.mark.parametrize("case", cases_for("tags"), ids=lambda case: case["id"])
def test_calorie_and_digestibility_tags_match_reference(case):
    assert compute_tags(NutrientSet.model_validate(case["input"])) == spanish_labels(
        case["expected_result"]
    )
