from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import NutrientSet


class CatalogSearchTooBroad(ValueError):
    """Candidates exceed the safe limit; resolution must remain ambiguous."""


class CatalogFood(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source: str
    source_id: str
    name: str
    name_en: str = ""
    state: str | None = None
    basis: Literal["100g"] = "100g"
    nutrients: NutrientSet = Field(default_factory=NutrientSet)


class CatalogQuery(BaseModel):
    food_name: str
    quantity: float | str | None = None
    unit: str = ""
    note: str = ""
    original_text: str = ""
    recipe_name: str = ""
    instructions: str = ""


class CatalogResolution(BaseModel):
    status: Literal["matched", "not_found", "ambiguous"]
    food: CatalogFood | None = None
    reason: str = ""
    method: str = "rules"
    confidence: float | None = None

    @model_validator(mode="after")
    def require_matched_food(self) -> Self:
        if self.status == "matched" and self.food is None:
            raise ValueError("A matched resolution requires a catalog food")
        if self.status != "matched" and self.food is not None:
            raise ValueError("An unresolved result cannot select a catalog food")
        return self
