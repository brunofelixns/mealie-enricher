from fastapi import APIRouter, Request

from ..compat import js_string
from .common import UNDEFINED, LegacyJSONResponse, internal_error, read_payload

router = APIRouter()


@router.post("/estimate")
async def estimate(request: Request) -> LegacyJSONResponse:
    body = await read_payload(request)
    if body is UNDEFINED or body is None:
        kind = "null" if body is None else "undefined"
        return internal_error(f"Cannot read properties of {kind} (reading 'content')")
    if not isinstance(body, dict) or "content" not in body or body["content"] is None:
        kind = (
            "null" if isinstance(body, dict) and body.get("content", False) is None else "undefined"
        )
        return internal_error(
            f"Cannot destructure property 'slug' of 'req.body.content' as it is {kind}."
        )
    content = body["content"]
    slug = js_string(content.get("slug", "undefined") if isinstance(content, dict) else "undefined")
    state = request.app.state
    state.tasks.start(
        state.queue.run(slug, "estimate", lambda: state.processing.process_estimate(slug))
    )
    return LegacyJSONResponse({"status": "accepted"}, status_code=202)
