"""Resolve catalog identity without estimating or replacing catalog nutrition."""

import asyncio
import hashlib
import json
import math
import re
from typing import Protocol

from pydantic import ValidationError

from .models import CatalogFood, CatalogQuery, CatalogResolution, CatalogSearchTooBroad
from .text import food_states, normalize_name

_VERSION = "catalog-resolver-v3"
_SEARCH_LIMIT = 100
_BOILED_STATE_WORDS = {"hervido", "hervida", "hervidos", "hervidas", "boiled"}
_GENERIC_STATE_WORDS = {
    "raw",
    "uncooked",
    "crudo",
    "cruda",
    "crudos",
    "crudas",
    "cooked",
    "cocido",
    "cocida",
    "cocidos",
    "cocidas",
} | _BOILED_STATE_WORDS
_STATE_PREFIX = re.compile(r"\b(?:en|ya) (?=(?:" + "|".join(sorted(_GENERIC_STATE_WORDS)) + r")\b)")
_TRIVIAL_INGREDIENT_WORDS = {
    "g",
    "kg",
    "mg",
    "ml",
    "l",
    "de",
    "del",
    "el",
    "la",
    "los",
    "las",
    "ya",
    "al",
    "gusto",
    "opcional",
    "aproximadamente",
    "aprox",
}


class CatalogReader(Protocol):
    @property
    def fingerprint(self) -> str: ...

    def search(self, name: str, limit: int = 20) -> list[CatalogFood]: ...


class DecisionSelector(Protocol):
    @property
    def signature(self) -> str: ...

    @property
    def min_confidence(self) -> float: ...

    async def choose(
        self,
        query: CatalogQuery,
        candidates: list[CatalogFood],
    ) -> tuple[str, float] | None: ...


class ResolutionCache(Protocol):
    async def get_catalog_resolution(self, key: str) -> CatalogResolution | None: ...

    async def set_catalog_resolution(self, key: str, result: CatalogResolution) -> None: ...


def _digest(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _state_text(value: str) -> str:
    normalized = re.sub(r"\bsin cocer\b", "crudo", normalize_name(value))
    return _STATE_PREFIX.sub("", normalized)


def _mentioned_states(value: str) -> set[str]:
    normalized = _state_text(value)
    states = food_states(normalized)
    if set(normalized.split()) & _BOILED_STATE_WORDS:
        states.add("cooked")
    return states


def _states(food: CatalogFood) -> set[str]:
    explicit = {food.state} if food.state in {"raw", "cooked"} else set()
    return explicit | _mentioned_states(" ".join((food.name, food.name_en, food.state or "")))


def _identity(value: str) -> str:
    # Keep frying, draining, canning, drying and other preparation distinctions.
    return " ".join(word for word in _state_text(value).split() if word not in _GENERIC_STATE_WORDS)


def _has_context(query: CatalogQuery) -> bool:
    ingredient_name = normalize_name(query.food_name)
    if any(
        normalize_name(value) not in {"", ingredient_name}
        for value in (query.note, query.recipe_name, query.instructions)
    ):
        return True
    redundant = set(normalize_name(query.food_name + " " + query.unit).split())
    redundant |= {"g", "kg", "mg", "ml", "l", "de", "del", "el", "la", "los", "las"}
    return any(
        word not in redundant and not re.fullmatch(r"\d+(?:g|kg|mg|ml|l)?", word)
        for word in normalize_name(query.original_text).split()
    )


def _rule_matches(
    query: CatalogQuery,
    candidates: list[CatalogFood],
    requested_states: set[str],
) -> list[CatalogFood]:
    # An unspecified exact entry is not evidence against other preparation variants.
    if not requested_states and len(candidates) != 1:
        return []
    redundant = set(normalize_name(query.food_name + " " + query.unit).split())
    redundant |= _GENERIC_STATE_WORDS | _TRIVIAL_INGREDIENT_WORDS
    qualifiers = _state_text(query.note + " " + query.original_text).split()
    if any(
        word not in redundant and not re.fullmatch(r"\d+(?:g|kg|mg|ml|l)?", word)
        for word in qualifiers
    ):
        return []
    identity = _identity(query.food_name)
    return [
        item
        for item in candidates
        if identity
        and (identity == _identity(item.name) or identity == _identity(item.name_en))
        and _states(item) == requested_states
    ]


class CatalogResolver:
    def __init__(
        self,
        catalog: CatalogReader,
        selector: DecisionSelector | None,
        cache: ResolutionCache,
    ) -> None:
        self.catalog = catalog
        self.selector = selector
        self.cache = cache

    @property
    def signature(self) -> str:
        return (
            _VERSION
            + ":"
            + _digest(
                {
                    "catalog": self.catalog.fingerprint,
                    "selector": self.selector.signature if self.selector is not None else None,
                }
            )
        )

    async def resolve(self, query: CatalogQuery) -> CatalogResolution:
        try:
            candidates = await asyncio.to_thread(
                self.catalog.search,
                query.food_name,
                limit=_SEARCH_LIMIT,
            )
            base_name = _identity(query.food_name)
            if not candidates and base_name and base_name != normalize_name(query.food_name):
                candidates = await asyncio.to_thread(
                    self.catalog.search,
                    base_name,
                    limit=_SEARCH_LIMIT,
                )
        except CatalogSearchTooBroad:
            return CatalogResolution(status="ambiguous", reason="catalog_search_too_broad")
        if len(candidates) >= _SEARCH_LIMIT:
            # A bounded reader must not turn a potentially truncated set into certainty.
            return CatalogResolution(status="ambiguous", reason="catalog_search_limit")
        key = "catalog-resolution:" + _digest(
            {
                "signature": self.signature,
                "query": query.model_dump(mode="json"),
                "candidates": [
                    item.model_dump(mode="json")
                    for item in sorted(candidates, key=lambda item: item.id)
                ],
            }
        )
        cached = self._cached(await self.cache.get_catalog_resolution(key), query, candidates)
        if cached is not None:
            return cached
        result = await self._resolve(query, candidates)
        # Provider failures share abstention: allow recovery on the next explicit estimate.
        if result.status == "matched" or result.method != "decisions":
            await self.cache.set_catalog_resolution(key, result)
        return result

    def _cached(
        self,
        value: object,
        query: CatalogQuery,
        candidates: list[CatalogFood],
    ) -> CatalogResolution | None:
        if value is None:
            return None
        try:
            raw = value.model_dump() if isinstance(value, CatalogResolution) else value
            result = CatalogResolution.model_validate(raw)
        except ValidationError, ValueError, TypeError:
            return None
        if result.method not in {"rules", "decisions"}:
            return None
        if (result.status == "not_found") != (not candidates):
            return None
        if result.confidence is not None and (
            not math.isfinite(result.confidence) or not 0 <= result.confidence <= 1
        ):
            return None
        if result.food is not None:
            current = next((item for item in candidates if item.id == result.food.id), None)
            if current is None:
                return None
            requested = _mentioned_states(
                " ".join((query.food_name, query.note, query.original_text))
            )
            if len(requested) > 1 or (requested and _states(current) not in (set(), requested)):
                return None
            if result.method == "rules":
                exact = _rule_matches(query, candidates, requested)
                if len(exact) != 1 or exact[0].id != current.id:
                    return None
            elif result.confidence is None or (
                result.confidence < getattr(self.selector, "min_confidence", 0.9)
                or not _has_context(query)
            ):
                return None
            return result.model_copy(update={"food": current})
        return result

    async def _resolve(
        self,
        query: CatalogQuery,
        candidates: list[CatalogFood],
    ) -> CatalogResolution:
        if not candidates:
            return CatalogResolution(status="not_found", reason="catalog_no_candidates")
        requested_states = _mentioned_states(
            " ".join(
                (
                    query.food_name,
                    query.note,
                    query.original_text,
                )
            )
        )
        if len(requested_states) > 1:
            return CatalogResolution(status="ambiguous", reason="conflicting_ingredient_state")
        compatible = [
            item
            for item in candidates
            if not requested_states or (not _states(item) or _states(item) == requested_states)
        ]
        if not compatible:
            return CatalogResolution(status="ambiguous", reason="incompatible_ingredient_state")
        exact = _rule_matches(query, compatible, requested_states)
        if len(exact) == 1:
            return CatalogResolution(
                status="matched",
                food=exact[0],
                reason="catalog_exact_identity",
                confidence=1,
            )
        if self.selector is not None and _has_context(query):
            choice = await self.selector.choose(query, compatible)
            if choice is not None:
                identifier, confidence = choice
                threshold = getattr(self.selector, "min_confidence", 0.9)
                selected = next((item for item in compatible if item.id == identifier), None)
                if selected is not None and (
                    isinstance(confidence, (int, float))
                    and not isinstance(confidence, bool)
                    and math.isfinite(confidence)
                    and threshold <= confidence <= 1
                ):
                    return CatalogResolution(
                        status="matched",
                        food=selected,
                        reason="decisions_selected",
                        method="decisions",
                        confidence=confidence,
                    )
            return CatalogResolution(
                status="ambiguous",
                reason="decisions_unresolved",
                method="decisions",
            )
        return CatalogResolution(status="ambiguous", reason="catalog_identity_ambiguous")
