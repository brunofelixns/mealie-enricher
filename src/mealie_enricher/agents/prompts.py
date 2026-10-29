def build_grams_prompt(unit_name: str, food_name: str) -> str:
    return (
        f"Estimate the weight in grams for 1 {unit_name} of {food_name}. "
        "Consider typical packaging sizes and food densities. Return ONLY a single number "
        "(the weight in grams). No explanation, no unit, no punctuation. "
        "If you cannot estimate, return 0."
    )


def build_nutrients_prompt(food_name: str) -> str:
    return (
        f'Estimate nutritional values per 100g for "{food_name}". Return ONLY valid JSON '
        'with these keys (all numbers, no units): {"kcal":0,"protein":0,"carbs":0,"fat":0,'
        '"saturatedFat":0,"transFat":0,"fiber":0,"sugar":0,"sodium":0,"cholesterol":0}. '
        "Use typical values for the food. No explanation, no markdown."
    )
