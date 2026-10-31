import asyncio

import pytest

from mealie_enricher.catalog.models import CatalogFood, CatalogQuery, CatalogResolution
from mealie_enricher.models import NutrientSet


def food(identifier, name, state=None):
    return CatalogFood(
        id=identifier,
        source="bedca",
        source_id=identifier,
        name=name,
        state=state,
        nutrients=NutrientSet(kcal_per100g=350 if state == "raw" else 130),
    )


RAW = food("bedca:raw", "Arroz crudo", "raw")
COOKED = food("bedca:cooked", "Arroz cocido", "cooked")


class Reader:
    fingerprint = "catalog-v1"

    def __init__(self, foods):
        self.foods = foods

    def search(self, name, limit=20):
        return self.foods[:limit]

    def get(self, identifier):
        return next((item for item in self.foods if item.id == identifier), None)


class SearchReader(Reader):
    """Search double preserving the real distinction between full and base lookup."""

    def __init__(self, matches):
        super().__init__([item for values in matches.values() for item in values])
        self.matches = matches
        self.lookups = []

    def search(self, name, limit=20):
        self.lookups.append((name, limit))
        return self.matches.get(name.casefold(), [])[:limit]


class Selector:
    signature = "selector-v1"
    min_confidence = 0.9

    def __init__(self, choice=None):
        self.choice = choice
        self.calls = []

    async def choose(self, query, candidates):
        self.calls.append((query, candidates))
        return self.choice


class Cache:
    def __init__(self):
        self.values = {}

    async def get_catalog_resolution(self, key):
        return self.values.get(key)

    async def set_catalog_resolution(self, key, result):
        self.values[key] = result


def resolver(foods, selector=None, cache=None):
    from mealie_enricher.catalog.resolver import CatalogResolver

    return CatalogResolver(Reader(foods), selector, cache or Cache())


@pytest.mark.parametrize(
    "query,want",
    [
        (CatalogQuery(food_name="Arroz crudo"), RAW),
        (CatalogQuery(food_name="Arroz", note="en crudo"), RAW),
        (CatalogQuery(food_name="Arroz", note="sin cocer"), RAW),
        (CatalogQuery(food_name="Arroz", note="ya cocido"), COOKED),
        (CatalogQuery(food_name="Arroz", original_text="200 g de arroz crudo"), RAW),
        (CatalogQuery(food_name="Arroz", original_text="200 g de arroz sin cocer"), RAW),
    ],
)
async def test_explicit_ingredient_state_resolves_without_external_selector(query, want):
    selection = Selector(("bedca:unknown", 0.99))
    result = await resolver([RAW, COOKED], selection).resolve(query)
    assert result.status == "matched"
    assert result.food == want
    assert result.method == "rules"
    assert selection.calls == []


@pytest.mark.parametrize(
    "foods,query",
    [
        ([RAW, COOKED], CatalogQuery(food_name="Arroz", original_text="200g arroz")),
        ([COOKED], CatalogQuery(food_name="Arroz")),
        (
            [RAW, COOKED],
            CatalogQuery(
                food_name="Arroz",
                recipe_name="Arroz cocido",
                instructions="Hervir el arroz y servir cocido",
            ),
        ),
        ([RAW, COOKED], CatalogQuery(food_name="Arroz crudo o cocido")),
        (
            [
                food("dry", "Garbanzos secos", "dry"),
                food("canned", "Garbanzos en conserva", "canned"),
            ],
            CatalogQuery(food_name="Garbanzos"),
        ),
        (
            [
                food("net", "Atún en conserva, peso neto", "canned"),
                food("drained", "Atún en conserva, escurrido", "drained"),
            ],
            CatalogQuery(food_name="Atún en conserva"),
        ),
    ],
)
async def test_incomplete_context_preserves_ambiguity(foods, query):
    result = await resolver(foods).resolve(query)
    assert result.status == "ambiguous"
    assert result.food is None


async def test_only_exact_generic_identity_is_selected_by_rules():
    salt = food("salt", "Sal")
    result = await resolver([salt]).resolve(CatalogQuery(food_name="sál"))
    assert result.status == "matched"
    assert result.food == salt
    assert (
        await resolver([salt]).resolve(CatalogQuery(food_name="Sal marina"))
    ).status == "ambiguous"


async def test_found_but_incompatible_state_remains_ambiguous():
    result = await resolver([COOKED]).resolve(CatalogQuery(food_name="Arroz crudo"))
    assert result.status == "ambiguous"


async def test_absent_food_is_distinguished_from_ambiguous_food():
    result = await resolver([]).resolve(CatalogQuery(food_name="Alimento desconocido"))
    assert result.status == "not_found"
    assert result.food is None


async def test_selector_can_choose_only_an_offered_compatible_id():
    selection = Selector((RAW.id, 0.96))
    result = await resolver([RAW, COOKED], selection).resolve(
        CatalogQuery(
            food_name="Arroz",
            instructions="Añadir al caldo y cocer veinte minutos",
        )
    )
    assert result.status == "matched"
    assert result.food == RAW
    assert result.method == "decisions"
    assert result.confidence == 0.96


@pytest.mark.parametrize(
    "choice",
    [
        ("unknown", 0.99),
        ("needs_context", 0.99),
        (RAW.id, 0.4),
        (RAW.id, float("nan")),
        (RAW.id, float("inf")),
        (RAW.id, 1.1),
        (RAW.id, True),
        None,
    ],
)
async def test_invalid_or_uncertain_selector_results_do_not_pick_a_candidate(choice):
    result = await resolver([RAW, COOKED], Selector(choice)).resolve(
        CatalogQuery(
            food_name="Arroz",
            note="para añadir al caldo",
        )
    )
    assert result.status == "ambiguous"
    assert result.food is None


async def test_confident_selector_cannot_invent_context_from_a_quantity():
    selection = Selector((COOKED.id, 0.999))
    result = await resolver([RAW, COOKED], selection).resolve(
        CatalogQuery(
            food_name="Arroz",
            quantity=200,
            unit="g",
            original_text="200g de arroz",
        )
    )
    assert result.status == "ambiguous"
    assert selection.calls == []


async def test_recipe_name_repeating_ingredient_is_not_evidence_of_food_state():
    selection = Selector((COOKED.id, 0.999))
    result = await resolver([RAW, COOKED], selection).resolve(
        CatalogQuery(
            food_name="Arroz",
            quantity=200,
            unit="g",
            recipe_name="Arroz",
            original_text="200 g arroz",
        )
    )
    assert result.status == "ambiguous"
    assert selection.calls == []


async def test_selector_receives_ingredient_and_recipe_context_but_no_conflicting_candidates():
    query = CatalogQuery(
        food_name="Arroz",
        note="crudo",
        recipe_name="Sopa",
        instructions="Cocer durante veinte minutos",
    )
    variant = food("brown", "Arroz integral crudo", "raw")
    selection = Selector((variant.id, 0.97))
    result = await resolver([COOKED, variant], selection).resolve(query)
    assert result.food == variant
    assert selection.calls[0] == (query, [variant])


async def test_cache_reuses_selection_only_for_the_same_full_context_and_candidates():
    cache = Cache()
    selection = Selector((RAW.id, 0.97))
    reader = Reader([RAW, COOKED])
    from mealie_enricher.catalog.resolver import CatalogResolver

    service = CatalogResolver(reader, selection, cache)
    query = CatalogQuery(food_name="Arroz", quantity=200, unit="g", note="para la sopa")
    assert (await service.resolve(query)).food == RAW
    selection.choice = None
    assert (await service.resolve(query)).food == RAW
    assert len(selection.calls) == 1
    for changes in [
        {"note": "para ensalada"},
        {"original_text": "200 g de arroz"},
        {"instructions": "usar sobras del día anterior"},
        {"recipe_name": "Sopa"},
        {"quantity": 100},
        {"unit": "ml"},
    ]:
        altered = CatalogQuery.model_validate({**query.model_dump(), **changes})
        assert (await service.resolve(altered)).status == "ambiguous"
    reader.fingerprint = "catalog-v2"
    assert (await service.resolve(query)).status == "ambiguous"
    selection.signature = "selector-v2"
    assert (await service.resolve(query)).status == "ambiguous"
    reader.foods = [COOKED]
    assert (await service.resolve(query)).status == "ambiguous"
    assert len(selection.calls) == 10


@pytest.mark.parametrize(
    "corrupt",
    [
        "not-json",
        {"status": "matched"},
        CatalogResolution(status="matched", food=food("other", "Otro alimento")),
    ],
)
async def test_corrupt_or_unoffered_cached_food_is_ignored(corrupt):
    cache = Cache()
    selection = Selector((RAW.id, 0.97))
    service = resolver([RAW, COOKED], selection, cache)
    query = CatalogQuery(food_name="Arroz", note="para la sopa")
    await service.resolve(query)
    key = next(iter(cache.values))
    cache.values[key] = corrupt
    assert (await service.resolve(query)).food == RAW
    assert len(selection.calls) == 2


async def test_signature_changes_with_catalog_and_selector_configuration():
    selection = Selector()
    service = resolver([RAW], selection)
    original = service.signature
    assert original == resolver([RAW], Selector()).signature
    service.catalog.fingerprint = "catalog-v2"
    assert service.signature != original
    updated = service.signature
    selection.signature = "selector-v2"
    assert service.signature != updated


async def test_catalog_errors_are_not_silently_converted_to_absent_food():
    service = resolver([RAW])

    def broken_search(name, limit=20):
        raise OSError("catalog file unreadable")

    service.catalog.search = broken_search
    with pytest.raises(OSError, match="unreadable"):
        await service.resolve(CatalogQuery(food_name="Arroz"))


async def test_sync_reader_runs_off_the_event_loop():
    service = resolver([])

    def threaded_search(name, limit=20):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        return []

    service.catalog.search = threaded_search
    assert (await service.resolve(CatalogQuery(food_name="Arroz"))).status == "not_found"


async def test_overbroad_search_remains_ambiguous_without_selector_or_fallback():
    from mealie_enricher.catalog.models import CatalogSearchTooBroad

    selection = Selector((RAW.id, 0.99))
    service = resolver([RAW], selection)

    def broad_search(name, limit=20):
        raise CatalogSearchTooBroad("more matches than the safe candidate limit")

    service.catalog.search = broad_search
    result = await service.resolve(CatalogQuery(food_name="Arroz", note="para la sopa"))
    assert result.status == "ambiguous"
    assert selection.calls == []


async def test_saturated_search_does_not_choose_a_unique_exact_match_after_truncation():
    foods = [food(str(index), f"Alimento {index}") for index in range(100)]
    result = await resolver(foods).resolve(CatalogQuery(food_name="Alimento 0"))
    assert result.status == "ambiguous"


async def test_cached_current_food_with_incompatible_state_is_ignored():
    cache = Cache()
    service = resolver([RAW, COOKED], cache=cache)
    query = CatalogQuery(food_name="Arroz crudo")
    await service.resolve(query)
    key = next(iter(cache.values))
    cache.values[key] = CatalogResolution(status="matched", food=COOKED, method="rules")
    assert (await service.resolve(query)).food == RAW


async def test_cached_decision_below_required_confidence_is_ignored():
    cache = Cache()
    service = resolver([RAW, COOKED], Selector((RAW.id, 0.97)), cache)
    query = CatalogQuery(food_name="Arroz", note="para la sopa")
    await service.resolve(query)
    key = next(iter(cache.values))
    cache.values[key] = CatalogResolution(
        status="matched",
        food=COOKED,
        method="decisions",
        confidence=0.2,
    )
    assert (await service.resolve(query)).food == RAW


@pytest.mark.parametrize("ingredient", ["Arroz cocido", "Arroz hervido", "Arroz boiled"])
async def test_state_alias_retries_base_lookup_and_uses_only_compatible_local_food(ingredient):
    from mealie_enricher.catalog.resolver import CatalogResolver

    generic = food("bedca:2660", "Arroz")
    boiled = food("bedca:2661", "Arroz, hervido", "cooked")
    reader = SearchReader({"arroz": [generic, boiled]})
    selection = Selector((generic.id, 0.99))
    service = CatalogResolver(reader, selection, Cache())
    result = await service.resolve(CatalogQuery(food_name=ingredient))
    assert result.status == "matched"
    assert result.food == boiled
    assert result.method == "rules"
    assert reader.lookups == [(ingredient, 100), ("arroz", 100)]
    assert selection.calls == []


async def test_state_alias_with_unknown_and_incompatible_foods_remains_ambiguous():
    from mealie_enricher.catalog.resolver import CatalogResolver

    reader = SearchReader({"arroz": [food("generic", "Arroz"), COOKED]})
    result = await CatalogResolver(reader, None, Cache()).resolve(
        CatalogQuery(food_name="Arroz crudo")
    )
    assert result.status == "ambiguous"
    assert result.food is None


async def test_exact_unspecified_food_does_not_hide_a_known_preparation_variant():
    generic = food("bedca:2660", "Arroz")
    boiled = food("bedca:2661", "Arroz, hervido", "cooked")
    selection = Selector((generic.id, 0.99))
    result = await resolver([generic, boiled], selection).resolve(
        CatalogQuery(
            food_name="Arroz",
            quantity=200,
            unit="g",
            original_text="200 g arroz",
        )
    )
    assert result.status == "ambiguous"
    assert selection.calls == []


@pytest.mark.parametrize(
    "note,candidate",
    [
        ("frito", COOKED),
        ("en aceite", food("generic", "Arroz")),
        ("cocido en aceite", COOKED),
        ("en conserva", food("generic", "Arroz")),
    ],
)
async def test_preparation_note_cannot_be_discarded_by_an_exact_generic_match(note, candidate):
    selection = Selector()
    result = await resolver([candidate], selection).resolve(
        CatalogQuery(food_name="Arroz", note=note)
    )
    assert result.status == "ambiguous"
    assert result.method == "decisions"
    assert selection.calls[0][0].note == note


async def test_original_preparation_qualifier_cannot_be_discarded_by_direct_rules():
    result = await resolver([COOKED]).resolve(
        CatalogQuery(
            food_name="Arroz",
            note="cocido",
            original_text="200g de arroz cocido en aceite",
        )
    )
    assert result.status == "ambiguous"


@pytest.mark.parametrize("qualifier", ["frito", "asado", "en conserva", "escurrido"])
async def test_state_alias_lookup_preserves_other_preparation_distinctions(qualifier):
    from mealie_enricher.catalog.resolver import CatalogResolver

    reader = SearchReader({"arroz": [COOKED]})
    query = CatalogQuery(food_name=f"Arroz cocido {qualifier}")
    result = await CatalogResolver(reader, None, Cache()).resolve(query)
    assert result.status == "not_found"
    assert reader.lookups == [(query.food_name, 100), (f"arroz {qualifier}", 100)]


async def test_saturated_alias_lookup_preserves_ambiguity():
    from mealie_enricher.catalog.resolver import CatalogResolver

    reader = SearchReader(
        {"arroz": [COOKED] + [food(str(index), f"Arroz variante {index}") for index in range(99)]}
    )
    result = await CatalogResolver(reader, None, Cache()).resolve(
        CatalogQuery(food_name="Arroz cocido")
    )
    assert result.status == "ambiguous"


@pytest.mark.parametrize("note", ["", "en aceite"])
async def test_cached_rule_match_cannot_bypass_preparation_checks(note):
    generic = food("generic", "Arroz")
    cache = Cache()
    service = resolver([generic, COOKED], cache=cache)
    query = CatalogQuery(food_name="Arroz", note=note)
    await service.resolve(query)
    key = next(iter(cache.values))
    cache.values[key] = CatalogResolution(status="matched", food=generic, confidence=1)
    assert (await service.resolve(query)).status == "ambiguous"


@pytest.mark.parametrize(
    "ingredient,want",
    [
        ("Arroz en crudo", RAW),
        ("Arroz sin cocer", RAW),
        ("Arroz ya cocido", COOKED),
    ],
)
async def test_spanish_state_phrase_in_name_keeps_base_alias_lookup(ingredient, want):
    from mealie_enricher.catalog.resolver import CatalogResolver

    reader = SearchReader({"arroz": [RAW, COOKED]})
    result = await CatalogResolver(reader, None, Cache()).resolve(
        CatalogQuery(food_name=ingredient)
    )
    assert result.food == want
    assert reader.lookups == [(ingredient, 100), ("arroz", 100)]


@pytest.mark.parametrize("note", ["en crudo en aceite", "sin cocer en aceite"])
async def test_recognized_state_phrase_does_not_erase_additional_preparation(note):
    result = await resolver([RAW]).resolve(CatalogQuery(food_name="Arroz", note=note))
    assert result.status == "ambiguous"


async def test_uncooked_phrase_does_not_conflict_silently_with_cooked_state():
    result = await resolver([RAW, COOKED]).resolve(
        CatalogQuery(food_name="Arroz", note="sin cocer o cocido")
    )
    assert result.status == "ambiguous"
