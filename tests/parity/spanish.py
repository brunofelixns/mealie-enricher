"""Apply the explicitly requested label change without altering upstream recordings."""

LABELS = {
    "Calories:Light": "Calorías:Bajas",
    "Calories:Moderate": "Calorías:Moderadas",
    "Calories:Hearty": "Calorías:Altas",
    "Calories:Heavy": "Calorías:Muy altas",
    "Digest:Easy": "Digestión:Fácil",
    "Digest:Moderate": "Digestión:Moderada",
    "Digest:Slow": "Digestión:Lenta",
    "Digest:Unknown": "Digestión:Desconocida",
    "calories-light": "calorias-bajas",
    "calories-moderate": "calorias-moderadas",
    "calories-hearty": "calorias-altas",
    "calories-heavy": "calorias-muy-altas",
    "digest-easy": "digestion-facil",
    "digest-moderate": "digestion-moderada",
    "digest-slow": "digestion-lenta",
    "digest-unknown": "digestion-desconocida",
}


def spanish_labels(value):
    if isinstance(value, dict):
        return {key: spanish_labels(item) for key, item in value.items()}
    if isinstance(value, list):
        return [spanish_labels(item) for item in value]
    if isinstance(value, str):
        for original, translated in LABELS.items():
            value = value.replace(original, translated)
    return value
