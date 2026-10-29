import json
import re
from urllib.parse import unquote_plus

from fastapi import APIRouter, Request

from .common import UNDEFINED, LegacyJSONResponse, internal_error, read_payload

router = APIRouter()


@router.post("/webhook")
async def webhook(request: Request) -> LegacyJSONResponse:
    body = await read_payload(request)
    if body is UNDEFINED or body is None:
        kind = "null" if body is None else "undefined"
        return internal_error(
            f"Cannot destructure property 'document_data' of 'req.body' as it is {kind}."
        )
    raw = body.get("document_data") if isinstance(body, dict) else None
    if raw is None or raw is False or raw == "" or raw == 0:
        return LegacyJSONResponse({"error": "Missing document_data"}, status_code=400)
    if isinstance(raw, str):
        try:
            if re.search(r"%(?![0-9a-fA-F]{2})", raw):
                raise ValueError("Invalid URI")
            parsed = json.loads(unquote_plus(raw, encoding="utf-8", errors="strict"))
        except ValueError, UnicodeError:
            return LegacyJSONResponse({"error": "Invalid document_data JSON"}, status_code=400)
    else:
        parsed = raw
    if not isinstance(parsed, dict):
        return LegacyJSONResponse({"error": "Invalid document_data"}, status_code=400)
    slug = parsed.get("recipe_slug")
    if slug is None:
        slug = parsed.get("recipeSlug")
    document_type = parsed.get("document_type")
    if document_type is None:
        document_type = parsed.get("documentType")
    if not isinstance(slug, str) or not isinstance(document_type, str):
        return LegacyJSONResponse({"error": "Invalid document_data"}, status_code=400)
    if document_type != "recipe":
        return LegacyJSONResponse({"status": "skipped", "reason": "not a recipe event"})
    state = request.app.state
    state.tasks.start(
        state.queue.run(slug, "webhook", lambda: state.processing.process_webhook(slug))
    )
    return LegacyJSONResponse({"status": "accepted"}, status_code=202)
