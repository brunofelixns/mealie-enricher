from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    retailer: str = "mercadona"
    brand: str = ""
    url: str = ""
    category: str = ""
    package_quantity: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    package_unit: Literal["g", "ml", "unit"] | None = None
    price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    available: bool = True
    variable_weight: bool = False
    drained_quantity: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    ingredients: str = ""
    nutrition: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    def evidence(self) -> dict[str, Any]:
        """Stable input for selection; acquisition timestamps never invalidate a choice."""
        return self.model_dump(mode="json", exclude={"raw"})


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retailer: str = "mercadona"
    postal_code: str
    warehouse: str
    observed_at: str
    fingerprint: str = ""
    products: list[Product]
