import copy

import pytest

from mealie_enricher.models import MealieIngredient


@pytest.mark.parametrize(
    "text,quantity,unit,food,grams",
    [
        ("8 unidad(es) Jamoncitos de pollo", 8, "unidad", "Jamoncitos de pollo", None),
        ("100 gramo(s) Quinoa", 100, "g", "Quinoa", None),
        ("100g de quinoa", 100, "g", "quinoa", None),
        ("1 berenjena", 1, "unidad", "berenjena", None),
        ("2 huevos", 2, "unidad", "huevos", None),
        ("una berenjena", 1, "unidad", "berenjena", None),
        ("1,5 kg patatas", 1.5, "kg", "patatas", None),
        ("1/2 cucharada de aceite de oliva", 0.5, "cucharada", "aceite de oliva", None),
        ("½ cucharadita de sal", 0.5, "cucharadita", "sal", None),
        ("1½ cups flour", 1.5, "cup", "flour", None),
        ("1 1/2 tablespoons olive oil", 1.5, "tablespoon", "olive oil", None),
        ("600 mililitro(s) Agua", 600, "ml", "Agua", None),
        ("2 cucharada(s) Aceite de oliva", 2, "cucharada", "Aceite de oliva", None),
        ("2 latas de atún de 80 g", 2, "lata", "atún", 160),
        ("1 sobre de pimentón (4 g)", 1, "sobre", "pimentón", 4),
        ("2 x 400 g tomate", 2, "envase", "tomate", 800),
        ("8 UNIDAD(ES) POLLO", 8, "unidad", "POLLO", None),
        ("1 GRAMO(S) sal", 1, "g", "sal", None),
        ("2 X 400 G tomate", 2, "envase", "tomate", 800),
        ("1 ½ cups flour", 1.5, "cup", "flour", None),
    ],
)
def test_recovery_preserves_explicit_food_quantities_and_units(text, quantity, unit, food, grams):
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    original = MealieIngredient(original_text=text, reference_id="source-line")
    before = copy.deepcopy(original.model_dump())
    recovered = recover_ingredient(original)
    assert recovered is not None
    assert recovered.pending_reason is None
    assert recovered.ingredient.quantity == quantity
    assert recovered.ingredient.unit.name == unit
    assert recovered.ingredient.food.name == food
    assert recovered.explicit_grams == grams
    assert original.model_dump() == before
    assert recovered.ingredient.reference_id == "source-line"


@pytest.mark.parametrize(
    "data,reason",
    [
        ({"originalText": "sal al gusto"}, "quantity_missing"),
        ({"originalText": "un chorrito de aceite"}, "quantity_imprecise"),
        ({"originalText": "1-2 tomates"}, "quantity_ambiguous"),
        ({"originalText": "1 sobre(s) Pimentón ahumado"}, "package_weight_unknown"),
        ({"originalText": "1 sobre(s) Tomillo seco"}, "package_weight_unknown"),
        ({"originalText": "1 bolsa de arroz"}, "package_weight_unknown"),
        ({"quantity": 2, "originalText": "3 huevos"}, "conflicting_quantity"),
        (
            {
                "quantity": 1,
                "food": {"name": "aceite de oliva"},
                "originalText": "1 cucharada de azúcar",
            },
            "conflicting_food",
        ),
        ({"originalText": "1/0 kg harina"}, "quantity_invalid"),
        ({"originalText": "2"}, "food_missing"),
        ({"originalText": "2 latas de atún de 0 g"}, "package_weight_invalid"),
        ({"originalText": "1/2-1 cebolla"}, "quantity_ambiguous"),
        ({"originalText": "½–1 cebolla"}, "quantity_ambiguous"),
        ({"originalText": "1 o 2 tomates"}, "quantity_ambiguous"),
        ({"originalText": "1 or 2 tomatoes"}, "quantity_ambiguous"),
        ({"originalText": "1 puñado de nueces"}, "quantity_imprecise"),
        (
            {"quantity": 1, "unit": {"name": "sobre"}, "originalText": "pimentón"},
            "package_weight_unknown",
        ),
    ],
)
def test_ambiguous_or_missing_data_stays_pending(data, reason):
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    original = MealieIngredient.model_validate(data)
    before = original.model_dump()
    recovered = recover_ingredient(original)
    assert recovered is not None
    assert recovered.pending_reason == reason
    assert original.model_dump() == before


def test_structured_food_and_valid_quantity_take_precedence_over_missing_fields():
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    original = MealieIngredient(
        quantity=1,
        food={"id": "keep-this-id", "name": "berenjena"},
        original_text="1 unidad(es) Berenjena",
    )
    recovered = recover_ingredient(original)
    assert recovered.pending_reason is None
    assert recovered.ingredient.quantity == 1
    assert recovered.ingredient.food.id == "keep-this-id"
    assert recovered.ingredient.food.name == "berenjena"
    assert recovered.ingredient.unit.name == "unidad"


@pytest.mark.parametrize(
    "data",
    [
        {"quantity": 100, "unit": {"name": "g"}, "food": {"name": "arroz"}},
        {
            "quantity": 100,
            "unit": {"name": "g"},
            "food": {"name": "arroz"},
            "originalText": "Different original text must not replace complete structured data",
        },
        {"quantity": 100, "unit": {"name": "g"}, "display": "rice"},
        {"quantity": 0, "originalText": "2 huevos"},
        {"quantity": -1, "originalText": "2 huevos"},
        {"quantity": "0,0", "originalText": "2 huevos"},
        {"quantity": "-0,5", "originalText": "2 huevos"},
    ],
)
def test_complete_legacy_or_explicitly_excluded_ingredients_are_unchanged(data):
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    assert recover_ingredient(MealieIngredient.model_validate(data)) is None


def test_recovery_metadata_explains_the_internal_view():
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    recovered = recover_ingredient(
        MealieIngredient(quantity=100, original_text="100 gramo(s) Quinoa", reference_id="quinoa")
    )
    metadata = recovered.metadata()
    assert metadata["source"] == "originalText"
    assert metadata["reference_id"] == "quinoa"
    assert metadata["original_text"] == "100 gramo(s) Quinoa"
    assert metadata["status"] == "recovered"
    assert metadata["food"] == "Quinoa"
    assert metadata["unit"] == "g"
    assert metadata["quantity"] == 100


def test_source_name_can_complete_known_mass_without_repeating_the_amount():
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    recovered = recover_ingredient(
        MealieIngredient(quantity=100, unit={"name": "g"}, original_text="Quinoa")
    )
    assert recovered.pending_reason is None
    assert recovered.ingredient.quantity == 100
    assert recovered.ingredient.food.name == "Quinoa"


def test_recovery_preserves_size_context_for_unit_weight_estimation():
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    recovered = recover_ingredient(
        MealieIngredient(quantity=1, food={"name": "tomate"}, original_text="1 tomate pequeño")
    )
    assert recovered.weight_food == "tomate pequeño"
    assert "pequeño" in recovered.context_text


def test_structured_size_is_retained_when_the_original_text_is_less_specific():
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    recovered = recover_ingredient(
        MealieIngredient(quantity=1, food={"name": "tomate grande"}, original_text="1 tomate")
    )
    assert recovered.pending_reason is None
    assert "grande" in recovered.weight_food


def test_known_structured_mass_is_not_replaced_by_an_inferred_piece_unit():
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    recovered = recover_ingredient(
        MealieIngredient(quantity=100, unit={"name": "g"}, original_text="100 Quinoa")
    )
    assert recovered.pending_reason is None
    assert recovered.ingredient.unit.name == "g"


def test_structured_decimal_comma_is_normalized_only_in_the_internal_view():
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    original = MealieIngredient(quantity="1,5", original_text="1,5 kg Quinoa")
    recovered = recover_ingredient(original)
    assert recovered.pending_reason is None
    assert recovered.ingredient.quantity == 1.5
    assert original.quantity == "1,5"


def test_preserved_package_unit_can_use_an_explicit_source_net_mass():
    from mealie_enricher.services.ingredient_recovery import recover_ingredient

    recovered = recover_ingredient(
        MealieIngredient(quantity=2, unit={"name": "sobre"}, original_text="pimentón (4 g)")
    )
    assert recovered.pending_reason is None
    assert recovered.ingredient.food.name == "pimentón"
    assert recovered.explicit_grams == 8
