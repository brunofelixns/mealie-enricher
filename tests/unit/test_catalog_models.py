import pytest

from mealie_enricher.catalog.models import CatalogFood, CatalogResolution
from mealie_enricher.models import NutrientSet


def test_catalog_preserves_unknown_nutrients():
    food = CatalogFood(
        id="bedca:1",
        source="bedca",
        source_id="1",
        name="Arroz crudo",
        nutrients=NutrientSet(kcal_per100g=350),
        state="raw",
    )
    assert food.nutrients.protein_per100g is None
    assert food.basis == "100g"


def test_match_requires_an_existing_catalog_food():
    with pytest.raises(ValueError, match="food"):
        CatalogResolution(status="matched")


def test_search_normalization_keeps_food_state_and_original_name():
    from mealie_enricher.catalog.text import food_states, normalize_name

    assert normalize_name(" Arroz, COCÍDO ") == "arroz cocido"
    assert food_states("Arroz crudo") == {"raw"}
    assert food_states("Arroz ya cocido") == {"cooked"}
    assert food_states("crudo o cocido") == {"raw", "cooked"}
