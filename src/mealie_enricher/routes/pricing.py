import hmac

from fastapi import APIRouter, HTTPException, Request

from ..pricing.service import PricingService
from .common import LegacyJSONResponse

router = APIRouter()


def _service(request: Request) -> PricingService:
    service = getattr(request.app.state, "pricing", None)
    if service is None:
        raise HTTPException(404, "Pricing disabled")
    if request.headers.get("origin"):
        raise HTTPException(403, "Cross-origin pricing requests are not allowed")
    expected = "Bearer " + request.app.state.settings.pricing.admin_token
    actual = request.headers.get("authorization", "")
    if not hmac.compare_digest(actual.encode(), expected.encode()):
        raise HTTPException(401, "Pricing control token required")
    return service


@router.get("/pricing/status")
async def status(request: Request) -> LegacyJSONResponse:
    return LegacyJSONResponse(_service(request).status())


@router.post("/pricing/sync")
async def sync(request: Request) -> LegacyJSONResponse:
    started = _service(request).trigger("manual")
    return LegacyJSONResponse({"status": "accepted" if started else "running"}, status_code=202)


@router.post("/pricing/refresh")
async def refresh(request: Request) -> LegacyJSONResponse:
    started = _service(request).trigger(
        "refresh", force=request.query_params.get("force") == "true"
    )
    return LegacyJSONResponse({"status": "accepted" if started else "running"}, status_code=202)
