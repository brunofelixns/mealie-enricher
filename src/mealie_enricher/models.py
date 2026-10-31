from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


def camel_case(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class WireModel(BaseModel):
    model_config = ConfigDict(alias_generator=camel_case, populate_by_name=True, extra="allow")


class MealieUnit(WireModel):
    id: str = ""
    name: str = ""
    plural_name: str | None = None
    abbreviation: str | None = None
    standard_quantity: float | str | None = None
    standard_unit: str | None = None


class MealieFood(WireModel):
    id: str = ""
    name: str = ""
    plural_name: str | None = None
    aliases: list[Any] | None = Field(default_factory=list)


class MealieIngredient(WireModel):
    quantity: float | str | None = None
    unit: MealieUnit | None = None
    food: MealieFood | None = None
    note: str | None = None
    display: str = ""
    title: str | None = None
    original_text: str | None = None
    reference_id: str | None = None


class MealieNutrition(WireModel):
    calories: str | None = None
    carbohydrate_content: str | None = None
    cholesterol_content: str | None = None
    fat_content: str | None = None
    fiber_content: str | None = None
    protein_content: str | None = None
    saturated_fat_content: str | None = None
    sodium_content: str | None = None
    sugar_content: str | None = None
    trans_fat_content: str | None = None
    unsaturated_fat_content: str | None = None


class MealieTag(WireModel):
    id: str = ""
    name: str
    slug: str
    group_id: str | None = None


class MealieRecipe(WireModel):
    slug: str
    name: str = ""
    recipe_yield: str | None = None
    recipe_yield_quantity: float | str | None = None
    recipe_servings: float | str | None = None
    recipe_ingredient: list[MealieIngredient] = Field(default_factory=list)
    nutrition: MealieNutrition | None = None
    tags: list[MealieTag] | None = None
    extras: dict[str, Any] | None = None
    household_id: str | None = None
    legacy_household_id: str | None = Field(default=None, alias="household_id")


class MealieRecipePatch(WireModel):
    nutrition: dict[str, str | None] | None = None
    extras: dict[str, Any] | None = None
    tags: list[MealieTag] | None = None


class NutrientSet(WireModel):
    kcal_per100g: float | None = None
    protein_per100g: float | None = None
    carbs_per100g: float | None = None
    fat_per100g: float | None = None
    saturated_fat_per100g: float | None = None
    trans_fat_per100g: float | None = None
    unsaturated_fat_per100g: float | None = None
    fiber_per100g: float | None = None
    sugar_per100g: float | None = None
    sodium_per100g: float | None = None
    cholesterol_per100g: float | None = None


class IngredientMatch(WireModel):
    name: str
    grams: float | None
    matched: bool
    nutrients: NutrientSet | None
    llm_estimated: bool | None = None


class IngredientOutcome(WireModel):
    food_name: str
    grams: float | None
    nutrients: NutrientSet | None
    llm_estimated: bool = False
    catalog: dict[str, Any] | None = Field(default=None, exclude=True)


class EstimateResult(WireModel):
    slug: str
    servings: float | str | None
    total_nutrients: NutrientSet
    per_serving_nutrients: NutrientSet
    matched_count: int
    unmatched_count: int
    unmatched_ingredients: list[str]
    matched_ingredients: list[IngredientMatch]


class NutritionPatch(WireModel):
    nutrition: dict[str, str | None] | None = None
    extras: dict[str, Any]


class OffLookupResult(WireModel):
    nutrients: NutrientSet | None
    matched: bool
    product_name: str | None


class ExecutionEstimate(WireModel):
    nutrients: NutrientSet
    matched_count: int
    unmatched_count: int


ExecutionStatus = Literal[
    "running", "processed", "tags-added", "manual", "skipped", "filtered", "error"
]
ExecutionTrigger = Literal["webhook", "estimate", "backfill"]


class ExecutionRecord(WireModel):
    id: str
    started_at: int
    updated_at: int
    finished_at: int | None = None
    duration_ms: int | None = None
    trigger: ExecutionTrigger
    slug: str
    recipe_name: str | None = None
    household_id: str | None = None
    status: ExecutionStatus = "running"
    changes: list[str] = Field(default_factory=list)
    estimate: ExecutionEstimate | None = None
    error: str | None = None


class ExecutionHandle(Protocol):
    def set_recipe(self, name: str, household_id: str | None) -> None: ...

    def complete(
        self,
        status: ExecutionStatus,
        changes: list[str],
        estimate: ExecutionEstimate | None = None,
    ) -> None: ...

    def fail(self, error: Exception | str) -> None: ...


class EstimateAndTagResult(WireModel):
    calories: float | None
    tag_slugs: list[str]
    per_serving_nutrients: NutrientSet
    matched_count: int
    unmatched_count: int


class MealieThemeColors(WireModel):
    primary: str
    accent: str
    secondary: str
    success: str
    info: str
    warning: str
    error: str


class MealieTheme(WireModel):
    light: MealieThemeColors
    dark: MealieThemeColors
