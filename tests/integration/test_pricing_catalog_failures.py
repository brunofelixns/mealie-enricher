"""Reject incomplete external catalogs and corrupted local versions safely."""

import json

import duckdb
import httpx
import pytest

from mealie_enricher.pricing.models import Product
from mealie_enricher.pricing.store import CatalogStore
from tests.integration.test_pricing_catalog import MercadonaAPI, download, make_snapshot


@pytest.mark.parametrize(
    "payload",
    [
        {"count": True, "results": []},
        {"count": 1, "results": "invalid"},
        {"count": 2, "results": [{"id": 1}]},
        {"count": 1, "results": [None]},
        {"count": 1, "results": [{"id": True}]},
        {"count": 1, "results": [{"id": 1, "categories": "invalid"}]},
        {"count": 2, "results": [{"id": 1}, {"id": 1}]},
        {"count": 1, "results": [{"id": 1}], "next": 123},
        {"count": 1, "results": [{"id": 1}], "next": "https://other.example/api/categories/"},
        {"count": 1, "results": [{"id": 1}], "next": "/api/products/1/"},
        {"count": 1, "results": [{"id": 1}], "next": "/api/categories/?wh=9999"},
        {"count": 1, "results": [{"id": 1}], "next": "/api/categories/"},
    ],
)
async def test_invalid_category_listing_cannot_produce_a_complete_snapshot(payload):
    api = MercadonaAPI()
    api.override["/api/categories"] = httpx.Response(200, json=payload)
    with pytest.raises(ValueError):
        await download(api)


async def test_category_count_changing_between_pages_rejects_the_import():
    api = MercadonaAPI()

    def page(request):
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json={"count": 3, "results": [{"id": 2}]})
        return httpx.Response(
            200, json={"count": 2, "results": [{"id": 1}], "next": "/api/categories/?page=2"}
        )

    api.override["/api/categories"] = page
    with pytest.raises(ValueError, match="count changed"):
        await download(api)


@pytest.mark.parametrize(
    "changes",
    [
        {"display_name": ""},
        {"price_instructions": None},
        {"details": ["invalid"]},
        {"nutrition_information": ["invalid"]},
    ],
)
async def test_malformed_product_details_abort_full_acquisition(changes):
    api = MercadonaAPI()
    api.products["100"].update(changes)
    with pytest.raises(ValueError, match="product details"):
        await download(api)


@pytest.mark.parametrize(
    "response", [httpx.Response(200, text="not-json"), httpx.Response(200, json=[])]
)
async def test_invalid_json_never_activates_as_a_catalog(response):
    api = MercadonaAPI()
    api.override["/api/categories"] = response
    with pytest.raises(ValueError, match="JSON"):
        await download(api)


async def test_invalid_scope_selection_body_is_rejected():
    api = MercadonaAPI()
    api.override["/api/postal-codes/actions/change-pc"] = httpx.Response(
        200, json={"warehouse_changed": "false"}, headers=api.scope_headers
    )
    with pytest.raises(ValueError, match="scope selection"):
        await download(api)


@pytest.mark.parametrize("value", ["not-a-number", "NaN", "Infinity", "-1"])
async def test_unusable_price_and_quantity_remain_unknown(value):
    api = MercadonaAPI()
    api.products["100"]["price_instructions"].update(unit_size=value, unit_price=value)
    api.products["100"]["nutrition_information"]["ingredients"] = None
    product = (await download(api)).products[0]
    assert product.price is None
    assert product.package_quantity is None
    assert product.ingredients == ""


@pytest.mark.parametrize(
    "changes",
    [
        {"observed_at": "2026-11-04T12:00:00"},
        {"products": [Product(id="1", name="Other", retailer="other")]},
        {"products": [Product(id="1", name="No unit", package_quantity=1)]},
    ],
)
def test_invalid_snapshot_does_not_replace_the_last_complete_version(tmp_path, changes):
    store = CatalogStore(str(tmp_path))
    fingerprint = store.publish(make_snapshot())
    with pytest.raises(ValueError):
        store.publish(make_snapshot(**changes))
    assert store.load("mercadona", "27004").fingerprint == fingerprint


@pytest.mark.parametrize(
    "corruption", ["manifest", "missing", "empty", "schema", "identity", "table", "bytes"]
)
def test_corrupt_active_catalog_is_rejected_instead_of_returning_partial_data(tmp_path, corruption):
    store = CatalogStore(str(tmp_path))
    store.publish(make_snapshot())
    manifest = tmp_path / "mercadona-27004.json"
    database = tmp_path / json.loads(manifest.read_text())["file"]
    if corruption == "manifest":
        manifest.write_text("not-json")
    elif corruption == "missing":
        database.unlink()
    elif corruption == "bytes":
        database.write_bytes(b"not-a-duckdb")
    else:
        with duckdb.connect(str(database)) as db:
            if corruption == "empty":
                db.execute("DELETE FROM snapshot_metadata")
            elif corruption == "schema":
                metadata = json.loads(
                    db.execute("SELECT metadata FROM snapshot_metadata").fetchone()[0]
                )
                metadata["schema_version"] = 999
                db.execute("UPDATE snapshot_metadata SET metadata = ?", [json.dumps(metadata)])
            elif corruption == "identity":
                product = json.loads(db.execute("SELECT product_json FROM products").fetchone()[0])
                product["name"] = "Modified after publication"
                db.execute("UPDATE products SET product_json = ?", [json.dumps(product)])
            else:
                db.execute("DROP TABLE products")
    with pytest.raises(ValueError):
        store.load("mercadona", "27004")


def test_missing_catalog_and_invalid_search_terms_do_not_return_products(tmp_path):
    store = CatalogStore(str(tmp_path))
    assert store.search("mercadona", "27004", "") == []
    assert store.search("mercadona", "27004", "rice") == []
    with pytest.raises(ValueError, match="too many"):
        store.search("mercadona", "27004", " ".join(str(i) for i in range(33)))
    store.publish(make_snapshot())
    (tmp_path / json.loads((tmp_path / "mercadona-27004.json").read_text())["file"]).unlink()
    with pytest.raises(ValueError, match="missing"):
        store.search("mercadona", "27004", "rice")
