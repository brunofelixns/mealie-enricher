import math
from pathlib import Path

from fastapi import APIRouter, Request
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.responses import HTMLResponse

from ..compat import js_number, json_stringify
from ..models import MealieTheme, MealieThemeColors
from .common import LegacyJSONResponse

router = APIRouter()
templates = Environment(
    loader=FileSystemLoader(Path(__file__).parents[1] / "templates"),
    autoescape=select_autoescape(["html"]),
    keep_trailing_newline=True,
)


def _theme_css(theme: MealieTheme) -> str:
    def colors(palette: MealieThemeColors) -> str:
        return "\n".join(f"    --{key}: {value};" for key, value in palette.model_dump().items())

    return (
        ":root {\n" + colors(theme.light) + "\n"
        "    --bg: #ffffff;\n"
        "    --surface: #ffffff;\n"
        "    --on-surface: 0, 0, 0;\n"
        "    --border-base: 0, 0, 0;\n"
        f"    --link: {theme.light.accent};\n"
        "  }\n"
        "  @media (prefers-color-scheme: dark) {\n"
        "    :root {\n" + colors(theme.dark) + "\n"
        "      --bg: #1e1e1e;\n"
        "      --surface: #1e1e1e;\n"
        "      --on-surface: 255, 255, 255;\n"
        "      --border-base: 255, 255, 255;\n"
        f"      --link: color-mix(in srgb, {theme.dark.accent} 78%, white);\n"
        "    }\n"
        "  }"
    )


@router.get("/estimator/history")
async def history_html(request: Request) -> HTMLResponse:
    theme = await request.app.state.theme.get_theme()
    return HTMLResponse(
        templates.get_template("history.html").render(
            theme_css=_theme_css(theme),
            theme=theme,
            recipe_url_json=json_stringify(request.app.state.settings.history.recipe_url_template),
        ),
        headers={"Cache-Control": "private, max-age=7200"},
    )


@router.get("/estimator/history.json")
async def history_json(request: Request) -> LegacyJSONResponse:
    values = request.query_params.getlist("since")
    since = js_number(values[0] if len(values) == 1 else values) if values else None
    if since is not None and not math.isfinite(since):
        return LegacyJSONResponse(
            {"error": "since must be a timestamp in milliseconds"}, status_code=400
        )
    return LegacyJSONResponse(
        [
            record.model_dump(by_alias=True)
            for record in request.app.state.history.get_history(since)
        ]
    )
