import json
import math
import re
from decimal import Decimal
from typing import Any


def js_number_str(value: float | int) -> str:
    number = float(value)
    if math.isnan(number):
        return "NaN"
    if math.isinf(number):
        return "Infinity" if number > 0 else "-Infinity"
    if number == 0:
        return "0"
    text = repr(number)
    if 1e-6 <= abs(number) < 1e21:
        fixed = format(Decimal(text), "f")
        return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed
    mantissa, separator, exponent = text.partition("e")
    if separator:
        mantissa = mantissa.removesuffix(".0")
        exp = int(exponent)
        return mantissa + "e" + ("+" if exp >= 0 else "-") + str(abs(exp))
    return text.removesuffix(".0")


def js_string(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return js_number_str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ",".join("" if item is None else js_string(item) for item in value)
    return "[object Object]"


def js_parse_int(value: Any) -> float:
    match = re.match(r"^[+-]?\d+", js_string(value).strip(), flags=re.ASCII)
    return float(int(match[0])) if match else math.nan


def js_parse_float(value: Any) -> float:
    match = re.match(
        r"^[+-]?(?:Infinity|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)",
        js_string(value).strip(),
        flags=re.ASCII,
    )
    return float(match[0]) if match else math.nan


def js_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (float, int)):
        return float(value)
    text = js_string(value).strip()
    if not text:
        return 0.0
    try:
        if re.fullmatch(r"0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+", text):
            return float(int(text, 0))
        if re.fullmatch(r"[+-]?(?:Infinity|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)", text, re.ASCII):
            return float(text)
    except ValueError, OverflowError:
        pass
    return math.nan


def js_round(value: float) -> float:
    if not math.isfinite(value) or value == 0:
        return value
    floor = math.floor(value)
    result = float(floor + (value - floor >= 0.5))
    return -0.0 if result == 0 and value < 0 else result


def js_divide(numerator: float, denominator: float) -> float:
    if denominator:
        return numerator / denominator
    if numerator == 0:
        return math.nan
    return math.copysign(math.inf, numerator * math.copysign(1, denominator))


def json_stringify(value: Any) -> str:
    def clean(item: Any) -> Any:
        if isinstance(item, float) and not math.isfinite(item):
            return None
        if isinstance(item, dict):
            return {key: clean(val) for key, val in item.items()}
        if isinstance(item, list):
            return [clean(val) for val in item]
        return item

    return json.dumps(clean(value), ensure_ascii=False, separators=(",", ":"))
