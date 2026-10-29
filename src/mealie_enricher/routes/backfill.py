from fastapi import APIRouter, Request

from .common import LegacyJSONResponse, read_payload

router = APIRouter()


@router.post("/backfill")
async def backfill(request: Request) -> LegacyJSONResponse:
    await read_payload(request)
    request.app.state.tasks.start(request.app.state.processing.process_backfill())
    return LegacyJSONResponse({"status": "accepted"}, status_code=202)
