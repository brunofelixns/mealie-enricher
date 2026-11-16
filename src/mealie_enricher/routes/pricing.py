import hmac
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request

from ..pricing.service import PricingService
from .common import LegacyJSONResponse

router = APIRouter()


def _service(request: Request) -> PricingService:
    service = getattr(request.app.state, "pricing", None)
    if service is None:
        raise HTTPException(404, "Pricing disabled")
    origin = request.headers.get("origin")
    if origin:
        try:
            source = urlsplit(origin)
            target = request.url
            same_origin = (
                source.scheme in {"http", "https"}
                and source.scheme == target.scheme
                and source.hostname == target.hostname
                and (source.port or (443 if source.scheme == "https" else 80))
                == (target.port or (443 if target.scheme == "https" else 80))
                and not (source.path or source.query or source.fragment or source.username)
            )
        except ValueError:
            same_origin = False
        if not same_origin:
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


@router.get("/pricing/progress")
async def progress(request: Request) -> LegacyJSONResponse:
    return LegacyJSONResponse(_service(request).progress_status())


@router.post("/pricing/refresh")
async def refresh(request: Request) -> LegacyJSONResponse:
    started = _service(request).trigger(
        "refresh", force=request.query_params.get("force") == "true"
    )
    return LegacyJSONResponse({"status": "accepted" if started else "running"}, status_code=202)


@router.post("/pricing/recipes/refresh")
async def refresh_recipes(request: Request) -> LegacyJSONResponse:
    service = _service(request)
    if not service.is_busy():
        available = await service.catalog_available()
        if not available and not service.is_busy():
            raise HTTPException(409, "Mercadona catalog unavailable; download the catalog first")
    started = service.trigger("refresh", force=True)
    return LegacyJSONResponse({"status": "accepted" if started else "running"}, status_code=202)
