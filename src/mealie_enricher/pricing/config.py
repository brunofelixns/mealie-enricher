from pydantic import BaseModel, Field


class PricingSettings(BaseModel):
    enabled: bool = False
    postal_code: str = Field(default="27004", pattern=r"^[0-9]{5}$")
    data_dir: str = "data/supermarkets"
    sync_interval_hours: float = Field(default=168, gt=0, le=87600, allow_inf_nan=False)
    auto_sync: bool = True
    request_delay_seconds: float = Field(default=2, ge=0, le=60, allow_inf_nan=False)
    max_products: int = Field(default=10000, ge=1, le=100000)
    max_candidates: int = Field(default=12, ge=2, le=99)
    max_decisions_per_run: int = Field(default=500, ge=1, le=10000)
    admin_token: str = Field(default="", repr=False, exclude=True)
