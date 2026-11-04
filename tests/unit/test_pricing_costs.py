import json
from decimal import Decimal

import pytest

from mealie_enricher.models import MealieIngredient, MealieRecipe
from mealie_enricher.pricing.models import Product


def ingredient(quantity=100, unit="g", name="Arroz", **extra):
    return MealieIngredient(
        quantity=quantity,
        unit={"name": unit} if isinstance(unit, str) else unit,
        food={"name": name},
        **extra,
    )


def product(**changes):
    return Product(
        **{
            "id": "rice",
            "name": "Arroz",
            "package_quantity": "1000",
            "package_unit": "g",
            "price": "1.50",
            **changes,
        }
    )


def recipe(*ingredients, servings=4, **changes):
    return MealieRecipe(
        slug="arroz",
        recipe_servings=servings,
        recipe_ingredient=list(ingredients),
        **changes,
    )


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        ("0,25", "kilogramos", (Decimal("250"), "g")),
        (2, "mg", (Decimal("0.002"), "g")),
        ("1.5", "L", (Decimal("1500"), "ml")),
        (2, "centilitros", (Decimal("20"), "ml")),
        (2, "unidades", (Decimal("2"), "unit")),
        ("0.1", "lb", (Decimal("45.359237"), "g")),
        (2, {"name": "custom", "abbreviation": "KG"}, (Decimal("2000"), "g")),
        (
            3,
            {"name": "cacito", "standardQuantity": "12.5", "standardUnit": "gram"},
            (Decimal("37.5"), "g"),
        ),
        (
            2,
            {"name": "g", "standardQuantity": "15", "standardUnit": "milliliter"},
            (Decimal("30"), "ml"),
        ),
        (None, "g", (None, None)),
        (0, "g", (None, None)),
        (-2, "g", (None, None)),
        ("NaN", "g", (None, None)),
        ("Infinity", "g", (None, None)),
        ("al gusto", "g", (None, None)),
        (2, None, (None, None)),
        (2, "pizcas", (None, None)),
        (2, "dientes", (None, None)),
        (2, "tazas", (None, None)),
        (2, {"name": "g", "standardQuantity": "-2", "standardUnit": "gram"}, (None, None)),
        (2, {"name": "g", "standardQuantity": 1, "standardUnit": "unknown"}, (None, None)),
        (2, {"name": "g", "standardQuantity": 1}, (None, None)),
        (None, "g", (None, None)),
    ],
)
def test_quantity_converts_only_explicit_compatible_units(quantity, unit, expected):
    from mealie_enricher.pricing.costs import ingredient_quantity

    assert ingredient_quantity(ingredient(quantity, unit)) == expected


def test_display_text_never_supplies_a_missing_measured_quantity():
    from mealie_enricher.pricing.costs import ingredient_quantity

    value = ingredient(None, "g", display="200 g arroz", original_text="200 g arroz")
    assert ingredient_quantity(value) == (None, None)


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"recipe_servings": "2,5", "recipe_yield_quantity": 8}, Decimal("2.5")),
        ({"recipe_servings": None, "recipe_yield_quantity": 3}, Decimal("3")),
        ({"recipe_servings": "NaN", "recipe_yield_quantity": 3}, Decimal("3")),
        ({"recipe_servings": -1, "recipe_yield_quantity": 0}, None),
        ({"recipe_servings": "Infinity"}, None),
        ({"recipe_yield": "12 cupcakes"}, None),
    ],
)
def test_servings_prefer_explicit_servings_then_numeric_yield(fields, expected):
    from mealie_enricher.pricing.costs import recipe_servings

    assert recipe_servings(MealieRecipe(slug="cake", **fields)) == expected


def test_costs_group_shared_packages_before_ceiling_and_keep_decimal_arithmetic():
    from mealie_enricher.pricing.costs import calculate_costs

    result = calculate_costs(recipe(ingredient(250), ingredient(500)), [product(), product()])
    assert result["complete"] is True
    assert result["total_cost"] == "1.13"
    assert result["known_total_cost"] == "1.13"
    assert result["per_serving_cost"] == "0.28"
    assert result["purchase_cost"] == "1.50"
    assert result["servings"] == "4"
    assert [line["cost"] for line in result["lines"]] == ["0.38", "0.75"]
    purchase = result["purchases"][0]
    assert purchase["packages"] == 1
    assert purchase["package_fraction"] == "0.75"
    assert purchase["leftover_quantity"] == "250"
    assert result["unresolved"] == []
    json.dumps(result, allow_nan=False)


def test_totals_round_only_after_summing_unrounded_costs():
    from mealie_enricher.pricing.costs import calculate_costs

    result = calculate_costs(
        recipe(ingredient(1), ingredient(1), ingredient(1), servings=2),
        [product(price="0.05", package_quantity="3")] * 3,
    )
    assert result["total_cost"] == "0.05"
    assert result["per_serving_cost"] == "0.03"
    assert result["purchase_cost"] == "0.05"
    assert result["purchases"][0]["packages"] == 1


def test_purchase_cost_ceils_grouped_required_packages():
    from mealie_enricher.pricing.costs import calculate_costs

    result = calculate_costs(recipe(ingredient(750), ingredient(750)), [product()] * 2)
    assert result["total_cost"] == "2.25"
    assert result["purchase_cost"] == "3.00"
    assert result["purchases"][0]["packages"] == 2
    assert result["purchases"][0]["leftover_quantity"] == "500"


def test_distinct_presentations_never_share_a_package_even_with_the_same_product_id():
    from mealie_enricher.pricing.costs import calculate_costs

    result = calculate_costs(
        recipe(ingredient(500), ingredient(500)),
        [product(), product(package_quantity="500", price="1.00")],
    )
    assert result["total_cost"] == "1.75"
    assert result["purchase_cost"] == "2.50"
    assert len(result["purchases"]) == 2


def test_missing_servings_suppresses_only_per_serving_amount():
    from mealie_enricher.pricing.costs import calculate_costs

    result = calculate_costs(recipe(ingredient(500), servings=None), [product()])
    assert result["complete"] is True
    assert result["total_cost"] == "0.75"
    assert result["purchase_cost"] == "1.50"
    assert result["per_serving_cost"] is None
    assert result["servings"] is None


@pytest.mark.parametrize(
    ("unknown", "selected", "reason"),
    [
        (ingredient(100), None, "missing_product"),
        (ingredient(None), product(), "missing_quantity"),
        (ingredient(100), product(price=None), "missing_price"),
        (ingredient(100), product(package_quantity=None), "missing_package"),
        (ingredient(100), product(available=False), "unavailable"),
        (ingredient(100), product(variable_weight=True), "variable_weight"),
        (ingredient(100, "ml"), product(), "incompatible_unit"),
        (ingredient(1, "unidad"), product(), "incompatible_unit"),
        (ingredient(100, note="escurrido"), product(), "missing_drained_quantity"),
        (ingredient(100, name="Arroz cocido"), product(name="Arroz crudo"), "incompatible_state"),
        (
            ingredient(100, name="Garbanzos secos"),
            product(name="Garbanzos cocidos"),
            "incompatible_state",
        ),
    ],
)
def test_any_unresolved_line_keeps_complete_totals_null(unknown, selected, reason):
    from mealie_enricher.pricing.costs import calculate_costs

    result = calculate_costs(recipe(ingredient(500), unknown), [product(), selected])
    assert result["complete"] is False
    assert result["total_cost"] is None
    assert result["per_serving_cost"] is None
    assert result["purchase_cost"] is None
    assert result["known_total_cost"] == "0.75"
    assert result["lines"][1]["cost"] is None
    assert result["lines"][1]["reason"] == reason
    assert result["unresolved"] == [{"index": 1, "ingredient": unknown.food.name, "reason": reason}]


def test_zero_price_is_known_and_omitted_selections_are_unresolved():
    from mealie_enricher.pricing.costs import calculate_costs

    result = calculate_costs(recipe(ingredient(500)), [product(price="0")])
    assert result["complete"] is True
    assert result["total_cost"] == "0.00"
    assert result["purchase_cost"] == "0.00"
    assert calculate_costs(recipe(ingredient(500)), [])["complete"] is False


def test_drained_content_is_used_only_for_explicit_drained_measurements():
    from mealie_enricher.pricing.costs import calculate_costs

    canned = product(
        name="Garbanzos cocidos", package_quantity="400", drained_quantity="240", price="1.20"
    )
    result = calculate_costs(
        recipe(ingredient(120, name="Garbanzos cocidos", note="peso escurrido")), [canned]
    )
    assert result["total_cost"] == "0.60"
    assert result["lines"][0]["basis"] == "drained"
    assert result["purchases"][0]["package_quantity"] == "400"
    assert result["purchases"][0]["drained_quantity"] == "240"
    assert result["purchases"][0]["leftover_quantity"] == "120"
    net = calculate_costs(recipe(ingredient(120, name="Garbanzos cocidos")), [canned])
    assert net["total_cost"] == "0.36"
    assert net["lines"][0]["basis"] == "net"


def test_mixed_net_and_drained_demands_group_as_fractions_without_inventing_leftovers():
    from mealie_enricher.pricing.costs import calculate_costs

    canned = product(
        name="Garbanzos cocidos", package_quantity="400", drained_quantity="240", price="1.20"
    )
    result = calculate_costs(
        recipe(
            ingredient(200, name="Garbanzos cocidos"),
            ingredient(120, name="Garbanzos cocidos", note="escurridos"),
        ),
        [canned, canned],
    )
    assert result["purchase_cost"] == "1.20"
    assert result["purchases"][0]["packages"] == 1
    assert result["purchases"][0]["leftover_quantity"] is None


def test_counted_package_does_not_need_an_invented_piece_weight():
    from mealie_enricher.pricing.costs import calculate_costs

    eggs = product(name="Huevos", package_quantity="6", package_unit="unit", price="1.80")
    result = calculate_costs(recipe(ingredient(2, "unidades", "Huevos")), [eggs])
    assert result["total_cost"] == "0.60"
    assert result["purchase_cost"] == "1.80"
    assert result["purchases"][0]["leftover_quantity"] == "4"


def test_empty_recipe_has_unknown_cost_instead_of_free_complete_recipe():
    from mealie_enricher.pricing.costs import calculate_costs

    result = calculate_costs(recipe(), [])
    assert result["complete"] is False
    assert result["total_cost"] is None
    assert result["purchase_cost"] is None
