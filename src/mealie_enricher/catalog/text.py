import re
import unicodedata


def normalize_name(value: str) -> str:
    folded = "".join(
        char
        for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )
    return " ".join(re.findall(r"[a-z0-9]+", folded))


def food_states(value: str) -> set[str]:
    tokens = set(normalize_name(value).split())
    states: set[str] = set()
    if tokens & {"crudo", "cruda", "crudos", "crudas", "raw", "uncooked"}:
        states.add("raw")
    if tokens & {
        "cocido",
        "cocida",
        "cocidos",
        "cocidas",
        "hervido",
        "hervida",
        "cooked",
        "boiled",
        "asado",
        "asada",
        "frito",
        "frita",
        "grilled",
        "fried",
        "roasted",
        "horneado",
        "horneada",
    }:
        states.add("cooked")
    return states
