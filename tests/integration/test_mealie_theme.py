import httpx
import respx

from mealie_enricher.config import MealieSettings
from mealie_enricher.services.mealie_theme import DEFAULT_THEME, MealieThemeClient


async def test_theme_validation_cache_ttl_and_preserved_base_path():
    now = [1000]
    with respx.mock as mock:
        route = mock.get("http://mealie.test/sub/api/app/about/theme").mock(
            return_value=httpx.Response(
                200,
                json={
                    "lightPrimary": " #aBc ",
                    "darkPrimary": "#ABCDEF",
                    "lightAccent": "red",
                    "darkError": "#１２３",
                },
            )
        )
        async with httpx.AsyncClient() as http:
            theme = MealieThemeClient(
                MealieSettings(url="http://mealie.test/sub///", timeout_ms=1234),
                http,
                clock_ms=lambda: now[0],
            )
            result = await theme.get_theme()
            assert result.light.primary == "#aBc"
            assert result.dark.primary == "#ABCDEF"
            assert result.light.accent == DEFAULT_THEME.light.accent
            assert result.dark.error == DEFAULT_THEME.dark.error
            assert route.calls.last.request.extensions["timeout"]["read"] == 1.234
            now[0] += 7200000 - 1
            assert await theme.get_theme() == result
            assert route.call_count == 1
            now[0] += 1
            await theme.get_theme()
            assert route.call_count == 2


async def test_theme_failure_is_cached_for_only_thirty_seconds():
    now = [0]
    with respx.mock as mock:
        route = mock.get("http://mealie.test/api/app/about/theme").mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json={"lightPrimary": "#123"})]
        )
        async with httpx.AsyncClient() as http:
            theme = MealieThemeClient(
                MealieSettings(url="http://mealie.test"), http, clock_ms=lambda: now[0]
            )
            assert await theme.get_theme() == DEFAULT_THEME
            now[0] = 29999
            assert await theme.get_theme() == DEFAULT_THEME
            assert route.call_count == 1
            now[0] = 30000
            assert (await theme.get_theme()).light.primary == "#123"
            assert route.call_count == 2
