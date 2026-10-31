"""Versioned persistent catalogs, independent of the application's SQLite cache."""

SCHEMA_VERSION = 1

NUTRIENT_FIELDS = (
    "kcal_per100g",
    "protein_per100g",
    "carbs_per100g",
    "fat_per100g",
    "saturated_fat_per100g",
    "trans_fat_per100g",
    "unsaturated_fat_per100g",
    "fiber_per100g",
    "sugar_per100g",
    "sodium_per100g",
    "cholesterol_per100g",
)

SCHEMA_SQL = """
CREATE TABLE catalog_metadata (key VARCHAR PRIMARY KEY, value JSON NOT NULL);
CREATE TABLE raw_foods (
    source VARCHAR NOT NULL, source_id VARCHAR NOT NULL, raw_json JSON NOT NULL,
    PRIMARY KEY(source, source_id)
);
CREATE TABLE raw_food_values (
    row_number INTEGER PRIMARY KEY, source VARCHAR NOT NULL, source_id VARCHAR NOT NULL,
    nutrient_code VARCHAR NOT NULL, unit VARCHAR NOT NULL, basis VARCHAR NOT NULL,
    value_text VARCHAR NOT NULL, raw_json JSON NOT NULL,
    UNIQUE(source, source_id, nutrient_code)
);
CREATE TABLE raw_units (row_number INTEGER PRIMARY KEY, raw_json JSON NOT NULL);
CREATE TABLE foods (
    id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, source_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL, name_en VARCHAR NOT NULL, state VARCHAR,
    normalized_name VARCHAR NOT NULL, normalized_name_en VARCHAR NOT NULL,
    basis VARCHAR NOT NULL CHECK (basis = '100g'),
    kcal_per100g DOUBLE, protein_per100g DOUBLE, carbs_per100g DOUBLE,
    fat_per100g DOUBLE, saturated_fat_per100g DOUBLE, trans_fat_per100g DOUBLE,
    unsaturated_fat_per100g DOUBLE, fiber_per100g DOUBLE, sugar_per100g DOUBLE,
    sodium_per100g DOUBLE, cholesterol_per100g DOUBLE
);
CREATE TABLE food_tokens (
    food_id VARCHAR NOT NULL, token VARCHAR NOT NULL, PRIMARY KEY(food_id, token)
);
CREATE INDEX food_tokens_lookup ON food_tokens(token);
CREATE TABLE retailers (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, source VARCHAR NOT NULL);
CREATE TABLE stores (
    id VARCHAR PRIMARY KEY, retailer_id VARCHAR NOT NULL REFERENCES retailers(id),
    name VARCHAR NOT NULL, location VARCHAR, source VARCHAR NOT NULL
);
CREATE TABLE products (
    id VARCHAR PRIMARY KEY, retailer_id VARCHAR REFERENCES retailers(id),
    source VARCHAR NOT NULL, source_id VARCHAR NOT NULL, name VARCHAR NOT NULL,
    brand VARCHAR, gtin VARCHAR, food_id VARCHAR REFERENCES foods(id), raw_json JSON
);
CREATE TABLE packages (
    id VARCHAR PRIMARY KEY, product_id VARCHAR NOT NULL REFERENCES products(id),
    quantity DECIMAL(18,6) NOT NULL CHECK (quantity > 0), unit VARCHAR NOT NULL,
    source VARCHAR NOT NULL
);
CREATE TABLE product_nutrients (
    product_id VARCHAR NOT NULL REFERENCES products(id),
    basis VARCHAR NOT NULL CHECK (basis IN ('100g', '100ml')),
    energy_kcal DOUBLE, protein_g DOUBLE, carbohydrates_g DOUBLE, fat_g DOUBLE,
    saturated_fat_g DOUBLE, trans_fat_g DOUBLE, unsaturated_fat_g DOUBLE,
    fiber_g DOUBLE, sugar_g DOUBLE, sodium_g DOUBLE, cholesterol_g DOUBLE,
    source VARCHAR NOT NULL, dataset_version VARCHAR NOT NULL, raw_json JSON,
    PRIMARY KEY(product_id, basis, source, dataset_version)
);
CREATE TABLE price_observations (
    id VARCHAR PRIMARY KEY, package_id VARCHAR NOT NULL REFERENCES packages(id),
    store_id VARCHAR REFERENCES stores(id), observed_at TIMESTAMPTZ NOT NULL,
    price DECIMAL(18,4) NOT NULL CHECK (price >= 0), currency VARCHAR NOT NULL,
    unit VARCHAR NOT NULL, is_offer BOOLEAN NOT NULL DEFAULT false,
    offer_description VARCHAR, source VARCHAR NOT NULL, source_url VARCHAR,
    raw_json JSON
);
"""

REQUIRED_COLUMNS = {
    "catalog_metadata": {"key", "value"},
    "raw_foods": {"source", "source_id", "raw_json"},
    "raw_food_values": {
        "row_number",
        "source",
        "source_id",
        "nutrient_code",
        "unit",
        "basis",
        "raw_json",
    },
    "raw_units": {"row_number", "raw_json"},
    "foods": {
        "id",
        "source",
        "source_id",
        "name",
        "name_en",
        "state",
        "normalized_name",
        "normalized_name_en",
        "basis",
        *NUTRIENT_FIELDS,
    },
    "food_tokens": {"food_id", "token"},
    "products": {"id", "source", "source_id", "name"},
    "product_nutrients": {
        "product_id",
        "basis",
        "energy_kcal",
        "protein_g",
        "carbohydrates_g",
        "fat_g",
        "saturated_fat_g",
        "trans_fat_g",
        "unsaturated_fat_g",
        "fiber_g",
        "sugar_g",
        "sodium_g",
        "cholesterol_g",
        "source",
        "dataset_version",
        "raw_json",
    },
    "packages": {"id", "product_id", "quantity", "unit"},
    "retailers": {"id", "name", "source"},
    "stores": {"id", "retailer_id", "name"},
    "price_observations": {
        "id",
        "package_id",
        "observed_at",
        "price",
        "currency",
        "unit",
        "is_offer",
        "source",
    },
}
