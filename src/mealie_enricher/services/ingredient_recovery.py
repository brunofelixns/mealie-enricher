"""Recover an estimation view without changing Mealie's source ingredient."""

import math
import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from ..catalog.text import normalize_name
from ..models import MealieFood, MealieIngredient, MealieUnit

RECOVERY_VERSION = "ingredient-recovery-v1"

_FRACTIONS = "¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"
_NUMBER = re.compile(rf"^([+-]?(?:\d+\s+)?\d+/\d+|\d*\s*[{_FRACTIONS}]|[+-]?\d+(?:[.,]\d+)?)")
_WORDS = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "medio": 0.5,
    "media": 0.5,
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "half": 0.5,
}
_UNITS: dict[str, str] = {}
for names, canonical in [
    ("g gr gramo gramos gram grams", "g"),
    ("kg kilogramo kilogramos kilogram kilograms", "kg"),
    ("mg miligramo miligramos milligram milligrams", "mg"),
    ("ml mililitro mililitros milliliter milliliters", "ml"),
    ("l litro litros liter liters", "l"),
    ("oz onza onzas ounce ounces", "oz"),
    ("lb libra libras pound pounds", "lb"),
    ("unidad unidades ud uds unit units pieza piezas piece pieces", "unidad"),
    ("cucharada cucharadas cda cdas", "cucharada"),
    ("cucharadita cucharaditas cdta cdtas", "cucharadita"),
    ("tablespoon tablespoons tbsp", "tablespoon"),
    ("teaspoon teaspoons tsp", "teaspoon"),
    ("taza tazas cup cups", "cup"),
    ("pizca pizcas pinch pinches", "pizca"),
    ("diente dientes clove cloves", "diente"),
    ("rebanada rebanadas slice slices", "rebanada"),
    ("sobre sobres sachet sachets", "sobre"),
    ("paquete paquetes packet packets pack packs", "paquete"),
    ("lata latas can cans tin tins", "lata"),
    ("bolsa bolsas bag bags", "bolsa"),
    ("bote botes jar jars", "bote"),
    ("botella botellas bottle bottles", "botella"),
    ("envase envases caja cajas carton cartons", "envase"),
]:
    _UNITS.update(dict.fromkeys(names.split(), canonical))
_PACKAGES = {"sobre", "paquete", "lata", "bolsa", "bote", "botella", "envase"}
_MASS = {"g": 1, "kg": 1000, "mg": 0.001, "oz": 28.35, "lb": 453.592}
_NET_MASS = re.compile(
    r"(?:\(\s*|\s+(?:de|of)\s+)(\d+(?:[.,]\d+)?)\s*(kg|mg|g)\s*\)?\s*$",
    re.IGNORECASE,
)


@dataclass
class RecoveredIngredient:
    ingredient: MealieIngredient
    recovered_fields: list[str]
    pending_reason: str | None = None
    explicit_grams: float | None = None
    context_text: str = ""
    weight_food: str = ""

    def metadata(self) -> dict[str, Any]:
        item = self.ingredient
        return {
            "source": "originalText",
            "reference_id": item.reference_id,
            "original_text": item.original_text,
            "status": "pending" if self.pending_reason else "recovered",
            "reason": self.pending_reason,
            "quantity": item.quantity,
            "unit": item.unit.name if item.unit else None,
            "food": item.food.name if item.food else None,
            "recovered_fields": self.recovered_fields,
        }


def _positive(value: float | str | None) -> float | None:
    try:
        number = float(str(value).replace(",", "."))
        return number if math.isfinite(number) and number > 0 else None
    except ValueError, TypeError:
        return None


def _amount(text: str) -> tuple[float | None, str, str | None]:
    match = _NUMBER.match(text)
    if match:
        token = match[0]
        try:
            if token[-1] in _FRACTIONS:
                value = float(token[:-1] or 0) + unicodedata.numeric(token[-1])
            elif "/" in token:
                pieces = token.split()
                value = float(Fraction(pieces[-1])) + (float(pieces[0]) if len(pieces) > 1 else 0)
            else:
                value = float(token.replace(",", "."))
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Nonpositive quantity")
            return value, text[match.end() :].strip(), None
        except ValueError, ZeroDivisionError, OverflowError:
            return None, text, "quantity_invalid"
    word, _, remaining = text.partition(" ")
    if word.casefold() in _WORDS:
        return _WORDS[word.casefold()], remaining.strip(), None
    return None, text, "quantity_missing"


def _unit(name: str) -> MealieUnit:
    if name in _MASS:
        return MealieUnit(name=name, standard_quantity=_MASS[name], standard_unit="gram")
    return MealieUnit(name=name)


def _clean_food(text: str) -> str:
    return re.sub(r"^(?:de(?:l)?|of)\s+", "", text.strip(), flags=re.IGNORECASE).strip()


def _compatible_food(known: str, parsed: str) -> bool:
    known_name, parsed_name = normalize_name(known), normalize_name(parsed)
    return (
        known_name == parsed_name
        or f" {known_name} " in f" {parsed_name} "
        or f" {parsed_name} " in f" {known_name} "
    )


def recover_ingredient(original: MealieIngredient) -> RecoveredIngredient | None:
    """Fill incomplete fields only; ambiguity is returned as a pending reason."""
    text = (original.original_text or "").strip()
    current_quantity = _positive(original.quantity)
    has_food = bool(original.food and original.food.name.strip())
    has_unit = bool(original.unit and original.unit.name.strip())
    if not text or (current_quantity is not None and has_food and has_unit):
        return None
    # Explicit exclusions must not be turned back into ingredients by the parser.
    if original.quantity is not None:
        try:
            if float(str(original.quantity).replace(",", ".")) <= 0:
                return None
        except ValueError:
            pass

    item = original.model_copy(deep=True)
    fields: list[str] = []
    if current_quantity is not None and isinstance(item.quantity, str):
        item.quantity = current_quantity
        fields.append("quantity")
    result = RecoveredIngredient(item, fields)
    quantity, remainder, reason = _amount(text)
    if quantity is not None and re.match(
        r"^(?:[-–—]|a\b|to\b|o\b|or\b|hasta\b)", remainder, re.IGNORECASE
    ):
        result.pending_reason = "quantity_ambiguous"
    result.pending_reason = result.pending_reason or reason
    if reason == "quantity_missing" and current_quantity is not None and has_unit:
        result.pending_reason = None
    if re.search(r"\b(?:chorritos?|poco|splash|some|punados?|handfuls?)\b", normalize_name(text)):
        result.pending_reason = "quantity_imprecise"

    if quantity is not None:
        if current_quantity is not None and not math.isclose(current_quantity, quantity):
            result.pending_reason = "conflicting_quantity"
        elif current_quantity is None:
            item.quantity = quantity
            fields.append("quantity")

    unit_name = "unidad" if quantity is not None else None
    explicit_unit = False
    mass_per_unit = None
    multipack = re.match(
        r"^[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|mg|g)\b\s*(.+)$", remainder, re.IGNORECASE
    )
    if multipack:
        explicit_unit = True
        unit_name = "envase"
        mass_per_unit = float(multipack[1].replace(",", ".")) * _MASS[multipack[2].lower()]
        food_name = multipack[3].strip()
    else:
        first, _, rest = remainder.partition(" ")
        key = normalize_name(first.casefold().replace("(es)", "es").replace("(s)", "s"))
        if key in _UNITS:
            explicit_unit = True
            unit_name = _UNITS[key]
            food_name = _clean_food(rest)
        else:
            food_name = _clean_food(remainder)
    if has_unit:
        assert item.unit is not None
        known = normalize_name(item.unit.name)
        known_unit = _UNITS.get(known, known)
        if explicit_unit and known_unit != unit_name:
            result.pending_reason = result.pending_reason or "conflicting_unit"
        if not explicit_unit:
            unit_name = known_unit
    elif unit_name is not None:
        item.unit = _unit(unit_name)
        fields.append("unit")

    if unit_name in _PACKAGES and mass_per_unit is None:
        net_mass = _NET_MASS.search(food_name)
        if net_mass:
            mass_per_unit = float(net_mass[1].replace(",", ".")) * _MASS[net_mass[2].lower()]
            food_name = food_name[: net_mass.start()].strip()
        else:
            result.pending_reason = result.pending_reason or "package_weight_unknown"

    weight_food = food_name
    if has_food:
        assert item.food is not None
        if food_name and not _compatible_food(item.food.name, food_name):
            result.pending_reason = result.pending_reason or "conflicting_food"
        if len(normalize_name(item.food.name)) > len(normalize_name(food_name)):
            weight_food = item.food.name
    elif food_name:
        item.food = MealieFood(name=food_name)
        fields.append("food")
    else:
        result.pending_reason = result.pending_reason or "food_missing"
    effective_quantity = quantity if quantity is not None else current_quantity
    if mass_per_unit is not None and effective_quantity is not None:
        grams = mass_per_unit * effective_quantity
        if math.isfinite(grams) and grams > 0:
            result.explicit_grams = grams
        else:
            result.pending_reason = result.pending_reason or "package_weight_invalid"
    result.weight_food = " ".join(part for part in (weight_food, item.note) if part)
    result.context_text = " ".join(
        str(part)
        for part in (quantity or current_quantity, unit_name, food_name)
        if part is not None
    )
    return result
