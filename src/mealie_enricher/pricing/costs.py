"""Price measured ingredients without estimating weights or mixing dimensions."""

import re
import unicodedata
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from math import ceil
from typing import Any

from ..models import MealieIngredient, MealieRecipe
from .models import Product

type _Presentation = tuple[str, str, Decimal | None, str | None, Decimal | None, Decimal | None]

_UNITS: dict[str, tuple[Decimal, str]] = {}
for _aliases, _factor, _dimension in [
    ("g gr gram grams gramo gramos gramm", "1", "g"),
    ("kg kilogram kilograms kilogramo kilogramos", "1000", "g"),
    ("mg milligram milligrams miligramo miligramos", "0.001", "g"),
    ("oz ounce ounces onza onzas", "28.349523125", "g"),
    ("lb lbs pound pounds libra libras", "453.59237", "g"),
    ("ml milliliter milliliters millilitre millilitres mililitro mililitros", "1", "ml"),
    ("cl centiliter centiliters centilitro centilitros", "10", "ml"),
    ("dl deciliter deciliters decilitro decilitros", "100", "ml"),
    ("l liter liters litre litres litro litros", "1000", "ml"),
    ("unit units unidad unidades ud uds u piece pieces pieza piezas", "1", "unit"),
]:
    _UNITS.update({alias: (Decimal(_factor), _dimension) for alias in _aliases.split()})


def _normalized(value: str) -> str:
    return (
        "".join(
            char
            for char in unicodedata.normalize("NFKD", value.casefold())
            if not unicodedata.combining(char)
        )
        .strip()
        .rstrip(".")
    )


def _number(value: Any, *, allow_zero: bool = False) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value).strip().replace(",", "."))
        return (
            result if result.is_finite() and (result >= 0 if allow_zero else result > 0) else None
        )
    except InvalidOperation, ValueError:
        return None


def _decimal(value: Decimal | Fraction) -> str:
    if isinstance(value, Fraction):
        value = Decimal(value.numerator) / Decimal(value.denominator)
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def _money(value: Decimal | Fraction) -> str:
    if isinstance(value, Fraction):
        value = Decimal(value.numerator) / Decimal(value.denominator)
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def ingredient_quantity(ingredient: MealieIngredient) -> tuple[Decimal | None, str | None]:
    """Return explicit quantity in g, ml or units; text cannot supply missing data."""
    quantity = _number(ingredient.quantity)
    unit = ingredient.unit
    if quantity is None or unit is None:
        return None, None
    if unit.standard_quantity is not None or unit.standard_unit is not None:
        # A supplied but invalid standard mapping must not silently fall back to its label.
        multiplier = _number(unit.standard_quantity)
        standard = _UNITS.get(_normalized(unit.standard_unit or ""))
        if multiplier is None or standard is None:
            return None, None
        factor, dimension = standard
        return quantity * multiplier * factor, dimension
    conversions = {
        _UNITS[name]
        for candidate in (unit.name, unit.abbreviation)
        if candidate and (name := _normalized(candidate)) in _UNITS
    }
    if len(conversions) != 1:
        return None, None
    factor, dimension = conversions.pop()
    return quantity * factor, dimension


def recipe_servings(recipe: MealieRecipe) -> Decimal | None:
    """Use Mealie's numeric serving fields, never infer servings from a dish name."""
    return _number(recipe.recipe_servings) or _number(recipe.recipe_yield_quantity)


def _ingredient_name(ingredient: MealieIngredient) -> str:
    return (
        ingredient.food.name
        if ingredient.food and ingredient.food.name
        else ingredient.display or ingredient.original_text or ingredient.note or ""
    )


def _ingredient_text(ingredient: MealieIngredient) -> str:
    return _normalized(
        " ".join(
            part
            for part in (
                _ingredient_name(ingredient),
                ingredient.note,
                ingredient.display,
                ingredient.original_text,
            )
            if part
        )
    )


def _states(text: str) -> set[str]:
    words = set(re.findall(r"[a-z]+", _normalized(text)))
    states = set()
    if words & {"raw", "crudo", "cruda", "crudos", "crudas"}:
        states.add("raw")
    if words & {"dry", "dried", "seco", "seca", "secos", "secas"}:
        states.add("dry")
    if words & {"cooked", "cocido", "cocida", "cocidos", "cocidas", "precocido", "precocidos"}:
        states.add("cooked")
    return states


def _incompatible_state(ingredient: MealieIngredient, product: Product) -> bool:
    measured = _states(_ingredient_text(ingredient))
    offered = _states(product.name)
    # Missing state is the selector's responsibility; explicit conflicts still block arithmetic.
    return bool(
        ("cooked" in measured and offered & {"raw", "dry"})
        or ("cooked" in offered and measured & {"raw", "dry"})
    )


def _line(
    ingredient: MealieIngredient, product: Product | None, index: int
) -> tuple[dict[str, Any], Fraction | None, Decimal | None]:
    quantity, dimension = ingredient_quantity(ingredient)
    drained = bool(re.search(r"\b(?:drained|escurrid[oa]s?)\b", _ingredient_text(ingredient)))
    basis = "drained" if drained else "net"
    result: dict[str, Any] = {
        "index": index,
        "ingredient": _ingredient_name(ingredient),
        "product_id": product.id if product else None,
        "product_name": product.name if product else None,
        "quantity": _decimal(quantity) if quantity is not None else None,
        "unit": dimension,
        "basis": basis,
        "cost": None,
        "reason": None,
    }
    reason = None
    package_quantity = None
    if product is None:
        reason = "missing_product"
    elif not product.available:
        reason = "unavailable"
    elif product.variable_weight:
        reason = "variable_weight"
    elif quantity is None or dimension is None:
        reason = "missing_quantity"
    elif _incompatible_state(ingredient, product):
        reason = "incompatible_state"
    elif _number(product.price, allow_zero=True) is None:
        reason = "missing_price"
    elif _number(product.package_quantity) is None or product.package_unit is None:
        reason = "missing_package"
    elif dimension != product.package_unit:
        reason = "incompatible_unit"
    elif drained and (dimension != "g" or _number(product.drained_quantity) is None):
        reason = "missing_drained_quantity"
    else:
        package_quantity = product.drained_quantity if drained else product.package_quantity
    result["reason"] = reason
    if reason is not None or product is None or quantity is None or package_quantity is None:
        return result, None, None
    # Validated above. Using Decimal also keeps an explicitly free product distinct from missing.
    price = Decimal(str(product.price))
    # Ratios are exact so recurring decimals cannot turn a true half-cent into 0.02499...
    fraction = Fraction(quantity) / Fraction(package_quantity)
    cost = fraction * Fraction(price)
    result["cost"] = _money(cost)
    return result, cost, package_quantity


def calculate_costs(recipe: MealieRecipe, selections: list[Product | None]) -> dict[str, Any]:
    """Price the consumed quantities and grouped whole packages independently of nutrition."""
    with localcontext() as context:
        context.prec = 50
        lines: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        products: dict[_Presentation, Product] = {}
        # Sum quantities with the same denominator before division to avoid rounding 1/3 three times.
        grouped: dict[_Presentation, dict[tuple[str, Decimal], Decimal]] = defaultdict(
            lambda: defaultdict(Decimal)
        )
        known_total = Fraction(0)
        for index, ingredient in enumerate(recipe.recipe_ingredient):
            selected = selections[index] if index < len(selections) else None
            line, cost, package_quantity = _line(ingredient, selected, index)
            lines.append(line)
            if cost is None:
                unresolved.append(
                    {"index": index, "ingredient": line["ingredient"], "reason": line["reason"]}
                )
                continue
            known_total += cost
            assert selected is not None and package_quantity is not None
            key: _Presentation = (
                selected.retailer,
                selected.id,
                selected.package_quantity,
                selected.package_unit,
                selected.price,
                selected.drained_quantity,
            )
            products[key] = selected
            grouped[key][(line["basis"], package_quantity)] += Decimal(line["quantity"])

        purchases: list[dict[str, Any]] = []
        purchase_total = Decimal(0)
        for key, requirements in grouped.items():
            selected = products[key]
            package_fraction = sum(
                (
                    Fraction(quantity) / Fraction(denominator)
                    for (_, denominator), quantity in requirements.items()
                ),
                Fraction(0),
            )
            packages = ceil(package_fraction)
            package_cost = Decimal(str(selected.price)) * packages
            purchase_total += package_cost
            leftover = None
            if len(requirements) == 1:
                (_, denominator), required = next(iter(requirements.items()))
                leftover = _decimal(denominator * packages - required)
            purchases.append(
                {
                    "product_id": selected.id,
                    "product_name": selected.name,
                    "package_quantity": _decimal(selected.package_quantity)
                    if selected.package_quantity is not None
                    else None,
                    "drained_quantity": _decimal(selected.drained_quantity)
                    if selected.drained_quantity is not None
                    else None,
                    "package_unit": selected.package_unit,
                    "package_price": _money(Decimal(str(selected.price))),
                    "package_fraction": _decimal(package_fraction),
                    "packages": packages,
                    "cost": _money(package_cost),
                    "leftover_quantity": leftover,
                    "basis": next(iter(requirements))[0] if len(requirements) == 1 else "mixed",
                }
            )

        complete = bool(lines) and not unresolved
        servings = recipe_servings(recipe)
        return {
            "total_cost": _money(known_total) if complete else None,
            "per_serving_cost": _money(known_total / Fraction(servings))
            if complete and servings is not None
            else None,
            "purchase_cost": _money(purchase_total) if complete else None,
            "known_total_cost": _money(known_total),
            "servings": _decimal(servings) if servings is not None else None,
            "complete": complete,
            "lines": lines,
            "purchases": purchases,
            "unresolved": unresolved,
        }
