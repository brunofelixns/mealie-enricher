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
