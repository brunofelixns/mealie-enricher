import asyncio
import json
from decimal import Decimal

import duckdb
import httpx
import pytest

from mealie_enricher.pricing.models import Product, Snapshot


def product_data(product_id="100", **overrides):
    data = {
        "id": product_id,
        "display_name": "Leche entera Hacendado",
        "brand": "Hacendado",
        "share_url": f"https://tienda.mercadona.es/product/{product_id}/leche",
        "published": True,
        "status": 1,
        "is_variable_weight": False,
        "price_instructions": {
            "unit_size": 1,
            "unit_price": "1.25",
            "size_format": "l",
            "total_units": None,
            "drained_weight": None,
            "is_pack": False,
            "approx_size": False,
            "selling_method": 0,
        },
        "details": {"brand": "Hacendado"},
        "nutrition_information": {"ingredients": "<p>Leche <b>entera</b>.</p>"},
    }
    data.update(overrides)
    return data


class MercadonaAPI:
    def __init__(self):
        self.calls = []
        self.products = {"100": product_data(), "101": product_data("101")}
        self.scope_headers = {"x-customer-wh": "4450", "x-customer-pc": "27004"}
        self.override = {}

    def __call__(self, request):
        self.calls.append(request)
        path = request.url.path.rstrip("/")
        if path in self.override:
            response = self.override[path]
            return response(request) if callable(response) else response
        if path == "/api/postal-codes/actions/retrieve-pc/27004":
            return httpx.Response(204)
        if path == "/api/postal-codes/actions/change-pc":
            assert json.loads(request.content) == {"new_postal_code": "27004"}
            return httpx.Response(
                200,
                json={"warehouse_changed": False},
                headers={**self.scope_headers, "set-cookie": "scope=fresh; Path=/"},
            )
        assert request.url.params["wh"] == "4450"
        assert "wrong" not in request.headers.get("cookie", "")
        if path == "/api/categories":
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [{"id": 1, "name": "Alimentación", "categories": [{"id": 11}]}],
                },
            )
        if path == "/api/categories/11":
            return httpx.Response(
                200,
                json={
                    "id": 11,
                    "name": "Lácteos",
                    "categories": [
                        {
                            "id": 111,
                            "name": "Leche",
                            "products": [{"id": pid} for pid in self.products],
                        }
                    ],
                },
            )
        if path.startswith("/api/products/"):
            return httpx.Response(200, json=self.products[path.rsplit("/", 1)[-1]])
        raise AssertionError(f"Unexpected request {request.method} {request.url}")


async def download(api, **kwargs):
    from mealie_enricher.pricing.mercadona import MercadonaClient

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(api), cookies={"old": "wrong"}
    ) as http:
        snapshot = await MercadonaClient(http, delay_seconds=0, **kwargs).download("27004")
        assert http.cookies.get("old") == "wrong"
        assert http.cookies.get("scope") is None
        return snapshot


async def test_download_scopes_all_reads_and_loads_details_after_complete_traversal():
    api = MercadonaAPI()
    snapshot = await download(api)
    assert snapshot.postal_code == "27004"
    assert snapshot.warehouse == "4450"
    assert len(snapshot.products) == 2
    product = snapshot.products[0]
    assert product.price == Decimal("1.25")
    assert product.package_quantity == Decimal("1000")
    assert product.package_unit == "ml"
    assert product.ingredients == "Leche entera."
    assert product.nutrition == {}
    assert product.category == "Leche"
    assert product.raw == api.products["100"]
    assert all(
        "wh" in req.url.params
        for req in api.calls
        if "/categories" in req.url.path or "/products" in req.url.path
    )
    assert "scope=fresh" in api.calls[-1].headers["cookie"]
    paths = [req.url.path for req in api.calls]
    assert paths.index("/api/categories/11/") < paths.index("/api/products/100/")


async def test_stalled_product_request_is_bounded_even_when_parent_timeout_is_disabled(monkeypatch):
    from mealie_enricher.pricing import mercadona

    api = MercadonaAPI()

    async def stalled(request):
        if request.url.path == "/api/products/100/":
            await asyncio.Future()
        return api(request)

    async def no_backoff(_seconds):
        pass

    monkeypatch.setattr(mercadona, "_REQUEST_TIMEOUT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(mercadona.asyncio, "sleep", no_backoff)
    async with httpx.AsyncClient(transport=httpx.MockTransport(stalled), timeout=None) as http:
        async with asyncio.timeout(0.25):
            with pytest.raises(ValueError, match="bounded retries"):
                await mercadona.MercadonaClient(http, delay_seconds=0).download("27004")


async def test_postal_preflight_uses_verified_retrieve_action_endpoint():
    api = MercadonaAPI()
    api.override["/api/postal-codes/27004"] = httpx.Response(404)
    await download(api)
    assert api.calls[0].url.path == "/api/postal-codes/actions/retrieve-pc/27004/"


@pytest.mark.parametrize("headers", [{}, {"x-customer-wh": "4450", "x-customer-pc": "28001"}])
async def test_rejects_unverified_postal_scope(headers):
    api = MercadonaAPI()
    api.scope_headers = headers
    with pytest.raises(ValueError, match="scope|postal|warehouse"):
        await download(api)
    assert not any("categories" in req.url.path for req in api.calls)


async def test_rejects_scope_drift_during_product_download():
    api = MercadonaAPI()
    api.override["/api/products/100"] = httpx.Response(
        200, json=product_data(), headers={"x-customer-wh": "9999"}
    )
    with pytest.raises(ValueError, match="scope|warehouse"):
        await download(api)


@pytest.mark.parametrize("payload", [{"id": 11}, {"id": 11, "products": "blocked"}])
async def test_rejects_malformed_or_partial_category(payload):
    api = MercadonaAPI()
    api.override["/api/categories/11"] = httpx.Response(200, json=payload)
    with pytest.raises(ValueError):
        await download(api)


async def test_product_limit_rejects_catalog_instead_of_truncating():
    with pytest.raises(ValueError, match="limit"):
        await download(MercadonaAPI(), max_products=1)


async def test_detail_identity_mismatch_rejects_complete_import():
    api = MercadonaAPI()
    api.products["100"]["id"] = "unrelated"
    with pytest.raises(ValueError, match="product|identity"):
        await download(api)


async def test_fresh_fish_variants_keep_distinct_dotted_product_ids(tmp_path):
    from mealie_enricher.pricing.store import CatalogStore

    api = MercadonaAPI()
    api.products = {
        product_id: product_data(product_id, display_name=name, is_variable_weight=True)
        for product_id, name in (
            ("81649.1", "Salmón a rodajas"),
            ("81649.4", "Salmón media pieza a rodajas"),
        )
    }
    snapshot = await download(api)
    store = CatalogStore(str(tmp_path))
    store.publish(snapshot)
    assert {p.id for p in store.load("mercadona", "27004").products} == set(api.products)
    assert {p.id for p in store.search("mercadona", "27004", "salmón")} == set(api.products)
    assert all(p.variable_weight and p.package_quantity is None for p in snapshot.products)


@pytest.mark.parametrize("product_id", ["81649.1", "81200.3"])
async def test_single_product_preflight_accepts_fish_variant_id(product_id):
    from mealie_enricher.pricing.mercadona import MercadonaClient

    api = MercadonaAPI()
    api.products = {product_id: product_data(product_id)}
    async with httpx.AsyncClient(transport=httpx.MockTransport(api)) as http:
        product = await MercadonaClient(http, delay_seconds=0).fetch_product("27004", product_id)
    assert product.id == product_id


@pytest.mark.parametrize("product_id", ["../1", "1/2", "1?wh=9", "1.2.3", ".1", "1.", "1e3"])
async def test_single_product_preflight_rejects_unsafe_or_malformed_ids(product_id):
    from mealie_enricher.pricing.mercadona import MercadonaClient

    api = MercadonaAPI()
    async with httpx.AsyncClient(transport=httpx.MockTransport(api)) as http:
        with pytest.raises(ValueError, match="identity"):
            await MercadonaClient(http, delay_seconds=0).fetch_product("27004", product_id)
    assert api.calls == []


async def test_unknown_or_variable_package_data_never_becomes_a_fixed_quantity():
    api = MercadonaAPI()
    api.products["100"]["price_instructions"]["size_format"] = "unknown"
    api.products["100"]["price_instructions"]["unit_price"] = None
    api.products["101"]["is_variable_weight"] = True
    snapshot = await download(api)
    assert snapshot.products[0].package_quantity is None
    assert snapshot.products[0].package_unit is None
    assert snapshot.products[0].price is None
    assert snapshot.products[1].variable_weight is True
    assert snapshot.products[1].package_quantity is None


@pytest.mark.parametrize(
    ("unit", "size", "units", "pack", "quantity", "expected_unit"),
    [
        ("kg", "0.5", None, False, "500", "g"),
        ("g", "125", None, False, "125", "g"),
        ("ml", "250", None, False, "250", "ml"),
        ("ud", "1", "6", True, "6", "unit"),
        ("l", "0.2", "3", True, "600", "ml"),
    ],
)
async def test_converts_only_explicit_known_package_units(
    unit, size, units, pack, quantity, expected_unit
):
    api = MercadonaAPI()
    api.products = {"100": product_data()}
    api.products["100"]["price_instructions"].update(
        size_format=unit, unit_size=size, total_units=units, is_pack=pack
    )
    if pack:
        base_quantity = Decimal(quantity) / (1000 if expected_unit in {"g", "ml"} else 1)
        api.products["100"]["price_instructions"]["bulk_price"] = str(
            Decimal("1.25") / base_quantity
        )
    product = (await download(api)).products[0]
    assert product.package_quantity == Decimal(quantity)
    assert product.package_unit == expected_unit


async def test_multipack_without_evidence_of_total_contents_stays_unknown():
    api = MercadonaAPI()
    api.products["100"]["price_instructions"].update(is_pack=True, total_units=6)
    product = (await download(api)).products[0]
    assert product.package_quantity is None
    assert product.package_unit is None


async def test_multipack_already_total_unit_size_is_not_multiplied_again():
    api = MercadonaAPI()
    api.products["100"]["price_instructions"].update(
        is_pack=True, total_units=6, unit_size=6, unit_price="6", bulk_price="1"
    )
    product = (await download(api)).products[0]
    assert product.package_quantity == Decimal("6000")


async def test_category_pagination_preserves_page_and_warehouse_query_parameters():
    api = MercadonaAPI()

    def category_page(request):
        if request.url.params.get("page") == "2":
            return httpx.Response(
                200,
                json={"count": 2, "next": None, "results": [{"id": 2, "categories": [{"id": 11}]}]},
            )
        return httpx.Response(
            200,
            json={
                "count": 2,
                "next": "https://tienda.mercadona.es/api/categories/?page=2&wh=4450",
                "results": [{"id": 1, "categories": [{"id": 11}]}],
            },
        )

    api.override["/api/categories"] = category_page
    assert len((await download(api)).products) == 2


async def test_duplicate_top_level_categories_are_not_proof_of_complete_catalog():
    api = MercadonaAPI()
    api.override["/api/categories"] = httpx.Response(
        200,
        json={
            "count": 2,
            "next": None,
            "results": [{"id": 11}, {"id": 11}],
        },
    )
    with pytest.raises(ValueError, match="duplicate|incomplete"):
        await download(api)


async def test_unsafe_redirect_never_receives_a_catalog_request():
    api = MercadonaAPI()
    api.override["/api/products/100"] = httpx.Response(
        302, headers={"location": "https://outside.example/api/products/100/?wh=4450"}
    )
    with pytest.raises(ValueError, match="unsafe|origin"):
        await download(api)
    assert not any(req.url.host == "outside.example" for req in api.calls)


async def test_availability_is_unknown_without_source_flags():
    api = MercadonaAPI()
    api.products["100"].pop("published")
    api.products["100"].pop("status")
    assert (await download(api)).products[0].available is False


async def test_published_product_with_live_null_status_is_available():
    api = MercadonaAPI()
    api.products["100"]["status"] = None
    assert (await download(api)).products[0].available is True


@pytest.mark.parametrize("status", [0, "unavailable", "unexpected"])
async def test_explicit_non_available_status_does_not_become_available(status):
    api = MercadonaAPI()
    api.products["100"]["status"] = status
    assert (await download(api)).products[0].available is False


async def test_invalid_weight_flags_cannot_turn_variable_product_into_fixed_package():
    api = MercadonaAPI()
    api.products["100"]["is_variable_weight"] = "true"
    with pytest.raises(ValueError, match="weight|flag"):
        await download(api)


async def test_ambiguous_drained_multipack_quantity_remains_unknown():
    api = MercadonaAPI()
    api.products["100"]["price_instructions"].update(
        size_format="kg",
        unit_size="0.4",
        total_units=2,
        is_pack=True,
        unit_price="1.25",
        bulk_price="3.125",
        drained_weight="0.3",
    )
    product = (await download(api)).products[0]
    assert product.package_quantity == Decimal("400")
    assert product.drained_quantity is None


async def test_transient_retry_honors_retry_after_and_redacts_error_bodies(monkeypatch):
    from mealie_enricher.pricing import mercadona

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(mercadona.asyncio, "sleep", fake_sleep)
    api = MercadonaAPI()
    retries = 0

    def retry(request):
        nonlocal retries
        retries += 1
        if retries < 2:
            return httpx.Response(429, text="private body", headers={"retry-after": "3"})
        return httpx.Response(200, json=api.products["100"])

    api.override["/api/products/100"] = retry
    await download(api)
    assert 3 in sleeps
    api.override["/api/products/100"] = httpx.Response(403, text="private body")
    with pytest.raises(ValueError) as error:
        await download(api)
    assert "403" in str(error.value)
    assert "private body" not in str(error.value)


async def test_single_product_preflight_uses_same_scope_validation():
    from mealie_enricher.pricing.mercadona import MercadonaClient

    api = MercadonaAPI()
    async with httpx.AsyncClient(transport=httpx.MockTransport(api)) as http:
        product = await MercadonaClient(http, delay_seconds=0).fetch_product("27004", "100")
    assert product.id == "100"
    assert not any("categories" in req.url.path for req in api.calls)


def make_snapshot(postal_code="27004", **overrides):
    data = dict(
        postal_code=postal_code,
        warehouse="4450",
        observed_at="2026-11-03T12:00:00+00:00",
        products=[
            Product(
                id="100",
                name="Leche entera",
                package_quantity="1000",
                package_unit="ml",
                price="1.25",
                raw={"source": 1},
            )
        ],
    )
    data.update(overrides)
    return Snapshot(**data)


def test_store_publishes_immutable_scoped_snapshots_and_persists_price_observations(tmp_path):
    from mealie_enricher.pricing.store import CatalogStore

    store = CatalogStore(str(tmp_path))
    first = make_snapshot()
    first_fingerprint = store.publish(first)
    initial_files = list(tmp_path.glob("*.duckdb"))
    assert len(initial_files) == 1
    previous_bytes = initial_files[0].read_bytes()
    changed = make_snapshot(
        observed_at="2026-11-04T12:00:00+00:00",
        products=[first.products[0].model_copy(update={"price": Decimal("1.35")})],
    )
    assert store.publish(changed) != first_fingerprint
    assert initial_files[0].read_bytes() == previous_bytes
    assert len(list(tmp_path.glob("*.duckdb"))) == 2
    assert CatalogStore(str(tmp_path)).load("mercadona", "27004").products[0].price == Decimal(
        "1.35"
    )
    assert store.load("mercadona", "28001") is None
    store.publish(make_snapshot("28001"))
    assert store.load("mercadona", "28001").postal_code == "28001"
    with duckdb.connect(str(initial_files[0]), read_only=True) as db:
        row = db.execute(
            "SELECT product_id, postal_code, warehouse, observed_at, price FROM price_observations"
        ).fetchone()
        assert row[:3] == ("100", "27004", "4450")
        assert str(row[3]).startswith("2026-11-03")
        assert Decimal(str(row[4])) == Decimal("1.25")
        assert db.execute("SELECT normal_name, raw FROM products").fetchone() == (
            "leche entera",
            '{"source":1}',
        )


def test_catalog_structured_price_and_package_columns_support_numeric_sql(tmp_path):
    from mealie_enricher.pricing.store import CatalogStore

    store = CatalogStore(str(tmp_path))
    store.publish(
        make_snapshot(
            products=[
                Product(
                    id="1", name="Large", price="10.50", package_quantity="1000", package_unit="g"
                ),
                Product(
                    id="2", name="Small", price="2.50", package_quantity="250", package_unit="g"
                ),
            ]
        )
    )
    with duckdb.connect(str(next(tmp_path.glob("*.duckdb"))), read_only=True) as db:
        assert [
            row[0] for row in db.execute("SELECT id FROM products ORDER BY price").fetchall()
        ] == ["2", "1"]
        assert (
            db.execute(
                "SELECT package_quantity / 1000 * price FROM products WHERE id = '2'"
            ).fetchone()[0]
            == 0.625
        )


def test_fingerprint_changes_for_new_competitor_but_not_observation_time_or_raw(tmp_path):
    from mealie_enricher.pricing.store import CatalogStore

    store = CatalogStore(str(tmp_path))
    snapshot = make_snapshot()
    fingerprint = store.publish(snapshot)
    again = snapshot.model_copy(deep=True)
    again.observed_at = "2026-11-04T12:00:00+00:00"
    again.products = [snapshot.products[0].model_copy(update={"raw": {"timestamp": "later"}})]
    assert store.publish(again) == fingerprint
    again.products.append(Product(id="101", name="Leche entera alternativa", price="1.1"))
    assert store.publish(again) != fingerprint
    assert len(store.search("mercadona", "27004", "LÉCHE")) == 2


def test_failed_manifest_activation_preserves_previous_snapshot(tmp_path, monkeypatch):
    from mealie_enricher.pricing import store as module

    store = module.CatalogStore(str(tmp_path))
    fingerprint = store.publish(make_snapshot())
    original_replace = module.os.replace

    def fail_manifest(source, target):
        if str(target).endswith(".json"):
            raise OSError("disk full")
        return original_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_manifest)
    with pytest.raises(OSError, match="disk full"):
        store.publish(make_snapshot(products=[Product(id="101", name="Competitor")]))
    assert store.load("mercadona", "27004").fingerprint == fingerprint


@pytest.mark.parametrize(
    "changes", [{"products": []}, {"warehouse": ""}, {"observed_at": "invalid"}]
)
def test_store_rejects_incomplete_snapshot_before_activation(tmp_path, changes):
    from mealie_enricher.pricing.store import CatalogStore

    store = CatalogStore(str(tmp_path))
    fingerprint = store.publish(make_snapshot())
    with pytest.raises(ValueError):
        store.publish(make_snapshot(**changes))
    assert store.load("mercadona", "27004").fingerprint == fingerprint


def test_search_matches_whole_normalized_tokens_safely(tmp_path):
    from mealie_enricher.pricing.store import CatalogStore

    store = CatalogStore(str(tmp_path))
    store.publish(
        make_snapshot(
            products=[
                Product(id="1", name="Arroz íntegro"),
                Product(id="2", name="Arroz cocido"),
                Product(id="3", name="Arroz integral", available=False),
            ]
        )
    )
    assert [p.id for p in store.search("mercadona", "27004", "ÍNTEGRO arroz")] == ["1"]
    assert store.search("mercadona", "27004", "arro") == []
    assert store.search("mercadona", "27004", "'; DROP TABLE products; --") == []
    assert len(store.search("mercadona", "27004", "arroz", limit=1)) == 1
    assert {p.id for p in store.search("mercadona", "27004", "arroz")} == {"1", "2"}
    for limit in (0, -1, 101):
        with pytest.raises(ValueError):
            store.search("mercadona", "27004", "arroz", limit=limit)


def test_manifest_rejects_cross_scope_or_path_traversal(tmp_path):
    from mealie_enricher.pricing.store import CatalogStore

    store = CatalogStore(str(tmp_path))
    store.publish(make_snapshot())
    manifest = next(tmp_path.glob("*.json"))
    data = json.loads(manifest.read_text())
    data["file"] = "../outside.duckdb"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        store.load("mercadona", "27004")
    with pytest.raises(ValueError):
        store.load("../other", "27004")
