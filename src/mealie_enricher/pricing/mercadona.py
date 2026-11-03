"""Scoped, paced acquisition of the Mercadona online assortment.

The caller owns the transport. Each operation owns a separate cookie jar, so a
previous postal-code selection cannot silently supply another area's prices.
"""

import asyncio
import math
import re
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Literal

import httpx

from .models import Product, Snapshot

_BASE_URL = "https://tienda.mercadona.es"
_REQUEST_TIMEOUT_SECONDS = 30.0


class _BorrowedTransport(httpx.AsyncBaseTransport):
    """Reuse configured proxy/test transports without sharing cookies or closing them."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http
        self.warehouse: str | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if (
            request.url.host != "tienda.mercadona.es"
            or request.url.scheme != "https"
            or request.url.port not in (None, 443)
            or request.url.userinfo
        ):
            raise ValueError("Mercadona returned an unsafe request origin")
        if request.url.path.startswith(("/api/categories", "/api/products")):
            warehouse = request.url.params.get("wh")
            if not warehouse or (self.warehouse is not None and warehouse != self.warehouse):
                raise ValueError("Mercadona redirect lost or changed the warehouse scope")
            self.warehouse = warehouse
        # HTTPX has no public transport accessor. Respect per-origin mounts too;
        # forwarding through http.send would mutate the caller's cookie jar.
        return await self.http._transport_for_url(request.url).handle_async_request(request)


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "br"}:
            self.parts.append(" ")


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parser = _PlainText()
    parser.feed(value)
    return " ".join("".join(parser.parts).split())


def _decimal(value: Any, *, positive: bool = True) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation, ValueError:
        return None
    if not number.is_finite() or number < 0 or (positive and number == 0):
        return None
    return number


def _identifier(value: Any) -> str:
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError("Mercadona returned an invalid category or product identity")
    return str(value)


def _product_identifier(value: Any) -> str:
    # Fresh-fish preparations have distinct IDs such as 81649.1 and 81649.4.
    # Preserve these opaque strings instead of treating them as decimal numbers.
    if type(value) not in (str, int) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", str(value)):
        raise ValueError("Mercadona returned an invalid product identity")
    return str(value)


def _postal_code(value: str) -> str:
    if not re.fullmatch(r"[0-9]{5}", value):
        raise ValueError("Mercadona requires a five-digit postal code")
    return value


def _product(data: Any, product_id: str, category: str = "") -> Product:
    if not isinstance(data, dict) or _product_identifier(data.get("id")) != product_id:
        raise ValueError("Mercadona product identity does not match the requested product")
    name = data.get("display_name")
    instructions = data.get("price_instructions")
    if not isinstance(name, str) or not name.strip() or not isinstance(instructions, dict):
        raise ValueError("Mercadona returned incomplete product details")
    details = data.get("details") or {}
    nutrition = data.get("nutrition_information") or {}
    if not isinstance(details, dict) or not isinstance(nutrition, dict):
        raise ValueError("Mercadona returned malformed product details")
    weight_flag = data.get("is_variable_weight", data.get("variable_weight", False))
    if not isinstance(weight_flag, bool):
        raise ValueError("Mercadona returned an invalid variable-weight flag")
    for flag in ("approx_size", "is_pack"):
        if flag in instructions and not isinstance(instructions[flag], bool):
            raise ValueError("Mercadona returned an invalid package flag")
    variable = weight_flag
    variable = variable or instructions.get("approx_size") is True
    variable = variable or instructions.get("selling_method", 0) not in (0, None)
    quantity = _decimal(instructions.get("unit_size"))
    unit: Literal["g", "ml", "unit"] | None = None
    units: dict[str, tuple[Literal["g", "ml", "unit"], int]] = {
        "kg": ("g", 1000),
        "g": ("g", 1),
        "l": ("ml", 1000),
        "ml": ("ml", 1),
        "ud": ("unit", 1),
        "unit": ("unit", 1),
    }
    conversion = units.get(str(instructions.get("size_format", "")).lower())
    if quantity is not None and conversion is not None and not variable:
        unit = conversion[0]
        quantity *= conversion[1]
        count = instructions.get("total_units")
        if instructions.get("is_pack") is True:
            pack_units = _decimal(count)
            bulk_price = _decimal(instructions.get("bulk_price"))
            pack_price = _decimal(instructions.get("unit_price"))
            if (
                pack_units is None
                or pack_units != pack_units.to_integral_value()
                or bulk_price is None
                or pack_price is None
            ):
                quantity, unit = None, None
            else:
                # Do not assume whether unit_size describes a pack or one item.
                # Only accept one interpretation corroborated by the source's price
                # per kg/l/unit, allowing its displayed two-decimal rounding.
                candidates = {quantity, quantity * pack_units}
                matching = [
                    candidate
                    for candidate in candidates
                    if abs(
                        bulk_price * candidate / (1000 if unit in {"g", "ml"} else 1) - pack_price
                    )
                    <= Decimal("0.02")
                ]
                if len(matching) == 1:
                    quantity = matching[0]
                else:
                    quantity, unit = None, None
        elif count is not None and _decimal(count) != Decimal(1):
            # A count without explicit pack semantics is ambiguous.
            quantity, unit = None, None
    else:
        quantity = None
    drained = _decimal(instructions.get("drained_weight"))
    # Multipack drained-weight semantics are not sufficiently explicit to choose
    # whether this field describes one container or the entire pack.
    if (
        drained is not None
        and quantity is not None
        and conversion is not None
        and conversion[0] == "g"
        and instructions.get("is_pack") is not True
    ):
        drained *= conversion[1]
        if drained > quantity:
            drained = None
    else:
        drained = None
    status = data.get("status")
    available = data.get("published") is True and status in (None, 1, "1", "available")
    nutrients = nutrition.get("nutrients", {})
    return Product(
        id=product_id,
        name=name.strip(),
        brand=str(data.get("brand") or details.get("brand") or ""),
        url=str(data.get("share_url") or ""),
        category=category,
        package_quantity=quantity,
        package_unit=unit,
        price=_decimal(instructions.get("unit_price"), positive=False),
        available=available,
        variable_weight=variable,
        drained_quantity=drained,
        ingredients=_text(nutrition.get("ingredients")),
        nutrition=nutrients if isinstance(nutrients, dict) else {},
        raw=data,
    )


class MercadonaClient:
    def __init__(
        self, http: httpx.AsyncClient, delay_seconds: float = 2, max_products: int = 10000
    ) -> None:
        if not math.isfinite(delay_seconds) or delay_seconds < 0:
            raise ValueError("Mercadona request delay must be finite and non-negative")
        if type(max_products) is not int or max_products < 1:
            raise ValueError("Mercadona product limit must be positive")
        self.http = http
        self.delay_seconds = delay_seconds
        self.max_products = max_products
        self._last_request: float | None = None
        self._lock = asyncio.Lock()

    def _session(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=_BASE_URL,
            transport=_BorrowedTransport(self.http),
            timeout=httpx.Timeout(_REQUEST_TIMEOUT_SECONDS),
            follow_redirects=True,
            headers={"accept": "application/json"},
        )

    async def _request(
        self, session: httpx.AsyncClient, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        for attempt in range(3):
            if self._last_request is not None:
                delay = self.delay_seconds - (time.monotonic() - self._last_request)
                if delay > 0:
                    await asyncio.sleep(delay)
            self._last_request = time.monotonic()
            try:
                async with asyncio.timeout(_REQUEST_TIMEOUT_SECONDS):
                    response = await session.request(method, url, **kwargs)
            except httpx.TransportError, TimeoutError:
                if attempt == 2:
                    raise ValueError("Mercadona transport failed after bounded retries") from None
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                delay = float(2**attempt)
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        try:
                            date = parsedate_to_datetime(retry_after)
                            delay = (date - datetime.now(UTC)).total_seconds()
                        except ValueError, TypeError, OverflowError:
                            pass
                if not math.isfinite(delay) or delay > 300:
                    raise ValueError("Mercadona retry delay exceeds the bounded retry window")
                await asyncio.sleep(max(0, delay))
                continue
            if not 200 <= response.status_code < 300:
                raise ValueError(f"Mercadona request failed with HTTP {response.status_code}")
            return response
        raise AssertionError("Unreachable retry state")

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            raise ValueError("Mercadona returned invalid JSON") from None
        if not isinstance(data, dict):
            raise ValueError("Mercadona returned an invalid JSON object")
        return data

    @staticmethod
    def _scope(response: httpx.Response, postal_code: str, warehouse: str = "") -> str:
        pc = response.headers.get("x-customer-pc")
        wh = response.headers.get("x-customer-wh")
        if not warehouse:
            if pc != postal_code or not wh or not re.fullmatch(r"[0-9]+", wh):
                raise ValueError("Mercadona did not verify the requested postal/warehouse scope")
            return wh
        if (pc is not None and pc != postal_code) or (wh is not None and wh != warehouse):
            raise ValueError("Mercadona postal/warehouse scope changed during acquisition")
        return warehouse

    async def _select(self, session: httpx.AsyncClient, postal_code: str) -> str:
        _postal_code(postal_code)
        await self._request(session, "GET", f"/api/postal-codes/actions/retrieve-pc/{postal_code}/")
        response = await self._request(
            session,
            "PUT",
            "/api/postal-codes/actions/change-pc/",
            json={"new_postal_code": postal_code},
        )
        data = self._json(response)
        if not isinstance(data.get("warehouse_changed"), bool):
            raise ValueError("Mercadona returned an invalid postal scope selection")
        return self._scope(response, postal_code)

    async def _get(
        self, session: httpx.AsyncClient, path: str, postal_code: str, warehouse: str
    ) -> dict[str, Any]:
        url = httpx.URL(_BASE_URL).join(path).copy_set_param("wh", warehouse)
        response = await self._request(session, "GET", str(url))
        self._scope(response, postal_code, warehouse)
        return self._json(response)

    async def fetch_product(self, postal_code: str, product_id: str) -> Product:
        """Validate a single live product without claiming a complete catalog import."""
        product_id = _product_identifier(product_id)
        async with self._lock, self._session() as session:
            warehouse = await self._select(session, postal_code)
            return _product(
                await self._get(session, f"/api/products/{product_id}/", postal_code, warehouse),
                product_id,
            )

    async def download(self, postal_code: str) -> Snapshot:
        async with self._lock, self._session() as session:
            warehouse = await self._select(session, postal_code)
            roots: list[dict[str, Any]] = []
            path = "/api/categories/"
            pages: set[str] = set()
            expected_count: int | None = None
            while path:
                if path in pages or len(pages) >= 100:
                    raise ValueError("Mercadona category pagination is incomplete or cyclic")
                pages.add(path)
                data = await self._get(session, path, postal_code, warehouse)
                results = data.get("results")
                count = data.get("count")
                if not isinstance(results, list) or type(count) is not int or count < 0:
                    raise ValueError("Mercadona returned invalid category listing")
                if expected_count is None:
                    expected_count = count
                elif expected_count != count:
                    raise ValueError("Mercadona category count changed during acquisition")
                roots.extend(results)
                next_page = data.get("next")
                if next_page is None:
                    break
                if not isinstance(next_page, str):
                    raise ValueError("Mercadona returned invalid category pagination")
                url = httpx.URL(next_page)
                if url.is_relative_url:
                    url = httpx.URL(_BASE_URL).join(next_page)
                if (
                    url.host != "tienda.mercadona.es"
                    or url.scheme != "https"
                    or url.path != "/api/categories/"
                ):
                    raise ValueError("Mercadona returned unsafe category pagination")
                if url.params.get("wh", warehouse) != warehouse:
                    raise ValueError("Mercadona pagination changed warehouse scope")
                path = str(url.copy_remove_param("wh"))
            if len(roots) != expected_count or not roots:
                raise ValueError("Mercadona category listing is incomplete or empty")
            root_ids = []
            for root in roots:
                if not isinstance(root, dict):
                    raise ValueError("Mercadona returned a malformed category")
                root_ids.append(_identifier(root.get("id")))
            if len(set(root_ids)) != len(root_ids):
                raise ValueError("Mercadona returned duplicate or incomplete category listings")
            category_ids: set[str] = set()
            pending: list[Any] = list(roots)
            while pending:
                node = pending.pop()
                if not isinstance(node, dict):
                    raise ValueError("Mercadona returned a malformed category")
                category_id = _identifier(node.get("id"))
                children = node.get("categories", [])
                if not isinstance(children, list):
                    raise ValueError("Mercadona returned malformed category children")
                if children:
                    pending.extend(children)
                else:
                    category_ids.add(category_id)
                if len(category_ids) + len(pending) > 10000:
                    raise ValueError("Mercadona category traversal exceeded its safety limit")
            product_categories: dict[str, str] = {}
            for category_id in sorted(category_ids):
                detail = await self._get(
                    session, f"/api/categories/{category_id}/", postal_code, warehouse
                )
                if _identifier(detail.get("id")) != category_id:
                    raise ValueError("Mercadona category identity changed")
                pending = [detail]
                while pending:
                    node = pending.pop()
                    if not isinstance(node, dict) or not (
                        "categories" in node or "products" in node
                    ):
                        raise ValueError("Mercadona returned incomplete category details")
                    children = node.get("categories", [])
                    products = node.get("products", [])
                    if not isinstance(children, list) or not isinstance(products, list):
                        raise ValueError("Mercadona returned malformed category details")
                    pending.extend(children)
                    for product in products:
                        if not isinstance(product, dict):
                            raise ValueError("Mercadona returned malformed product listing")
                        product_id = _product_identifier(product.get("id"))
                        product_categories.setdefault(product_id, str(node.get("name") or ""))
                        if len(product_categories) > self.max_products:
                            raise ValueError("Mercadona complete catalog exceeds the product limit")
            if not product_categories:
                raise ValueError("Mercadona returned an empty or incomplete catalog")
            products_out = []
            for product_id, category in sorted(product_categories.items()):
                detail = await self._get(
                    session, f"/api/products/{product_id}/", postal_code, warehouse
                )
                products_out.append(_product(detail, product_id, category))
            return Snapshot(
                postal_code=postal_code,
                warehouse=warehouse,
                observed_at=datetime.now(UTC).isoformat(),
                products=products_out,
            )
