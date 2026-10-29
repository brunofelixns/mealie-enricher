import json
from typing import Any

from fastapi import Request
from starlette.responses import JSONResponse

from ..compat import json_stringify

UNDEFINED = object()


class PayloadError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code = status, code


class LegacyJSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def render(self, content: Any) -> bytes:
        return json_stringify(content).encode("utf-8", "backslashreplace")


def internal_error(message: str) -> LegacyJSONResponse:
    return LegacyJSONResponse(
        {"statusCode": 500, "error": "Internal Server Error", "message": message}, status_code=500
    )


async def read_payload(request: Request) -> Any:
    raw = await request.body()
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not raw and not content_type:
        return UNDEFINED
    if content_type == "text/plain":
        return raw.decode("utf-8", errors="replace")
    if content_type != "application/json":
        raise PayloadError(415, "FST_ERR_CTP_INVALID_MEDIA_TYPE", "Unsupported Media Type")
    if not raw:
        raise PayloadError(
            400,
            "FST_ERR_CTP_EMPTY_JSON_BODY",
            "Body cannot be empty when content-type is set to 'application/json'",
        )
    try:

        def invalid_constant(value: str) -> None:
            raise ValueError(value)

        return json.loads(raw, parse_constant=invalid_constant)
    except (ValueError, UnicodeError) as error:
        raise PayloadError(
            400,
            "FST_ERR_CTP_INVALID_JSON_BODY",
            "Body is not valid JSON but content-type is set to 'application/json'",
        ) from error
