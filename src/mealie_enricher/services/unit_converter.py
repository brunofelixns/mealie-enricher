from ..compat import js_number
from ..models import MealieUnit

FALLBACK_UNITS: dict[str, float] = {}
for names, factor in [
    ("cup cups", 240),
    ("tablespoon tablespoons tbsp", 15),
    ("teaspoon teaspoons tsp", 5),
    ("ml milliliter milliliters", 1),
    ("l liter liters", 1000),
    ("gram grams gramm gramms g", 1),
    ("kilogram kilograms kg", 1000),
    ("ounce ounces oz", 28.35),
    ("pound pounds lb lbs", 453.592),
    ("pinch pinches", 0.5),
    ("dash dashes", 0.3),
    ("clove cloves", 5),
]:
    FALLBACK_UNITS.update(dict.fromkeys(names.split(), factor))

STANDARD_UNITS = {
    name: factor
    for names, factor in [
        ("g gram grams ml milliliter milliliters", 1),
        ("kg kilogram kilograms l liter liters", 1000),
        ("oz ounce ounces", 28.35),
        ("lb lbs pound pounds", 453.592),
    ]
    for name in names.split()
}


def convert_to_grams(quantity: float, unit: MealieUnit | None) -> float | None:
    if unit is None:
        return None
    if unit.standard_quantity is not None and unit.standard_unit is not None:
        factor = STANDARD_UNITS.get(unit.standard_unit.lower().strip())
        if factor is not None:
            return js_number(unit.standard_quantity) * factor * quantity
    for candidate in [unit.name, unit.abbreviation]:
        if candidate:
            name = candidate.lower().strip()
            if name in {"piece", "pieces", "slice", "slices"}:
                return None
            if name in FALLBACK_UNITS:
                return quantity * FALLBACK_UNITS[name]
    return None
