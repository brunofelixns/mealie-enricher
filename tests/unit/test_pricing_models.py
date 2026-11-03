from decimal import Decimal

import pytest
from pydantic import ValidationError


def test_product_stable_evidence_tracks_price_but_not_raw_metadata():
    from mealie_enricher.pricing.models import Product

    product = Product(id="1", name="Arroz", price="2.00", package_quantity="1000", package_unit="g")
    assert product.price == Decimal("2.00")
    assert product.evidence() == product.model_copy(update={"raw": {"updated": "later"}}).evidence()
    assert product.evidence() != product.model_copy(update={"price": Decimal("2.10")}).evidence()


@pytest.mark.parametrize(
    "field,value", [("price", "-1"), ("price", "NaN"), ("package_quantity", "0")]
)
def test_product_rejects_invalid_prices_and_quantities(field, value):
    from mealie_enricher.pricing.models import Product

    with pytest.raises(ValidationError):
        Product(id="1", name="Arroz", **{field: value})
