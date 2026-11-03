import json
import time
from collections.abc import Callable
from typing import Any, Self

from pydantic import ValidationError
from sqlalchemy import Table, delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from ..catalog.models import CatalogResolution
from ..compat import json_stringify
from ..models import NutrientSet
from .database import conflict_insert, create_database_engine, migrate_database
from .schema import (
    catalog_resolution_cache,
    llm_estimate_cache,
    llm_nutrient_cache,
    nutrient_cache,
)


class SqlCache:
    def __init__(self, engine: AsyncEngine, ttl_ms: float, clock_ms: Callable[[], float]) -> None:
        self.engine, self.ttl_ms, self.clock_ms = engine, ttl_ms, clock_ms

    @classmethod
    async def open(
        cls,
        path: str,
        ttl_ms: float,
        *,
        clock_ms: Callable[[], float] | None = None,
        database_url: str = "",
    ) -> Self:
        engine = create_database_engine(database_url, path)
        cache = cls(engine, ttl_ms, clock_ms or (lambda: time.time() * 1000))
        try:
            await migrate_database(engine)
            async with engine.begin() as conn:
                for table in (
                    nutrient_cache,
                    llm_estimate_cache,
                    llm_nutrient_cache,
                    catalog_resolution_cache,
                ):
                    await conn.execute(
                        delete(table).where(table.c.updated_at < cache.clock_ms() - ttl_ms)
                    )
        except BaseException:
            await engine.dispose()
            raise
        return cache

    async def close(self) -> None:
        await self.engine.dispose()

    async def _get(self, table: Table, key_column: str, key: str, value: str) -> Any:
        async with self.engine.begin() as conn:
            row = (
                (await conn.execute(select(table).where(table.c[key_column] == key)))
                .mappings()
                .first()
            )
            if row is None:
                return None
            if self.clock_ms() - row["updated_at"] > self.ttl_ms:
                await conn.execute(delete(table).where(table.c[key_column] == key))
                return None
            return row[value]

    async def _set(self, table: Table, key_column: str, key: str, column: str, value: Any) -> None:
        values = {key_column: key, column: value, "updated_at": int(self.clock_ms())}
        statement = (
            conflict_insert(self.engine, table)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[key_column],
                set_={column: value, "updated_at": values["updated_at"]},
            )
        )
        async with self.engine.begin() as conn:
            await conn.execute(statement)

    async def get_nutrients(self, food_name: str) -> NutrientSet | None:
        value = await self._get(nutrient_cache, "food_name", food_name.lower().strip(), "nutrients")
        try:
            return NutrientSet.model_validate(json.loads(value)) if value is not None else None
        except json.JSONDecodeError:
            return None

    async def set_nutrients(self, food_name: str, nutrients: NutrientSet) -> None:
        await self._set(
            nutrient_cache,
            "food_name",
            food_name.lower().strip(),
            "nutrients",
            json_stringify(nutrients.model_dump(by_alias=True)),
        )

    async def get_grams(self, unit_name: str, food_name: str) -> float | None:
        key = unit_name.lower().strip() + "|" + food_name.lower().strip()
        return await self._get(llm_estimate_cache, "lookup_key", key, "grams")

    async def set_grams(self, unit_name: str, food_name: str, grams: float) -> None:
        key = unit_name.lower().strip() + "|" + food_name.lower().strip()
        await self._set(llm_estimate_cache, "lookup_key", key, "grams", grams)

    async def get_llm_nutrients(self, food_name: str) -> NutrientSet | None:
        value = await self._get(
            llm_nutrient_cache, "food_name", food_name.lower().strip(), "nutrients"
        )
        try:
            return NutrientSet.model_validate(json.loads(value)) if value is not None else None
        except json.JSONDecodeError:
            return None

    async def set_llm_nutrients(self, food_name: str, nutrients: NutrientSet) -> None:
        await self._set(
            llm_nutrient_cache,
            "food_name",
            food_name.lower().strip(),
            "nutrients",
            json_stringify(nutrients.model_dump(by_alias=True)),
        )

    async def get_catalog_resolution(self, key: str) -> CatalogResolution | None:
        value = await self._get(catalog_resolution_cache, "lookup_key", key, "resolution")
        if value is None:
            return None
        try:
            return CatalogResolution.model_validate_json(value)
        except ValidationError, ValueError, TypeError:
            return None

    async def set_catalog_resolution(self, key: str, result: CatalogResolution) -> None:
        await self._set(
            catalog_resolution_cache,
            "lookup_key",
            key,
            "resolution",
            result.model_dump_json(),
        )


# Compatibility for existing integrations importing the original cache class.
SqliteCache = SqlCache
