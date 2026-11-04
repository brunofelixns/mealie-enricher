from sqlalchemy import BigInteger, Column, Float, MetaData, Table, Text

metadata = MetaData()
nutrient_cache = Table(
    "nutrient_cache",
    metadata,
    Column("food_name", Text, primary_key=True),
    Column("nutrients", Text, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)
unmatched_foods = Table(
    "unmatched_foods",
    metadata,
    Column("food_name", Text, primary_key=True),
    Column("updated_at", BigInteger, nullable=False),
)
llm_estimate_cache = Table(
    "llm_estimate_cache",
    metadata,
    Column("lookup_key", Text, primary_key=True),
    Column("grams", Float, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)
llm_nutrient_cache = Table(
    "llm_nutrient_cache",
    metadata,
    Column("food_name", Text, primary_key=True),
    Column("nutrients", Text, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)
catalog_resolution_cache = Table(
    "catalog_resolution_cache",
    metadata,
    Column("lookup_key", Text, primary_key=True),
    Column("resolution", Text, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)
execution_history = Table(
    "execution_history",
    metadata,
    Column("id", Text, primary_key=True),
    Column("started_at", BigInteger, nullable=False, index=True),
    Column("updated_at", BigInteger, nullable=False, index=True),
    Column("slug", Text, nullable=False, index=True),
    Column("status", Text, nullable=False, index=True),
    Column("payload", Text, nullable=False),
)
