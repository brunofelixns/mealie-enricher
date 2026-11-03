"""Integrated pricing lifecycle, independent from nutritional estimation."""

import asyncio
import hashlib
import json
import logging
import time
from contextlib import suppress
from decimal import Decimal
from typing import Any

import httpx

from ..catalog.text import normalize_name
from ..clients.mealie import MealieClient, get_recipe_household_id
from ..config import Settings
from ..models import MealieRecipe, MealieRecipePatch
from ..runtime.slug_queue import SlugQueue
from .costs import calculate_costs
from .mercadona import MercadonaClient
from .models import Product, Snapshot
from .selection import ProductSelector
from .state import PricingOwner, PricingState
from .store import CatalogStore

logger = logging.getLogger(__name__)
PRICING_EXTRA = "mealie_enricher_pricing"


class PricingDeferred(RuntimeError):
    """A later bounded batch must finish this valuation."""


def _recipe_input(recipe: MealieRecipe) -> dict[str, Any]:
    extra = recipe.model_extra or {}
    instructions = extra.get("recipeInstructions", [])
    if isinstance(instructions, list):
        instructions = [
            {key: step[key] for key in ("text", "title") if key in step}
            if isinstance(step, dict)
            else step
            for step in instructions
        ]
    return {
        "household": get_recipe_household_id(recipe),
        "name": recipe.name,
        "ingredients": [
            line.model_dump(mode="json", exclude={"reference_id"})
            for line in recipe.recipe_ingredient
        ],
        "description": extra.get("description", ""),
        "instructions": instructions,
        "servings": [recipe.recipe_servings, recipe.recipe_yield_quantity, recipe.recipe_yield],
    }


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _metadata(recipe: MealieRecipe) -> dict[str, Any]:
    raw = (recipe.extras or {}).get(PRICING_EXTRA)
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError, TypeError:
        return {"schema_version": 1, "retailers": {}}
    if not isinstance(value, dict) or not isinstance(value.get("retailers"), dict):
        return {"schema_version": 1, "retailers": {}}
    return value


class PricingService:
    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient,
        mealie: MealieClient,
        queue: SlugQueue,
        *,
        selector: ProductSelector | None = None,
    ) -> None:
        self.settings, self.config = settings, settings.pricing
        if len(self.config.admin_token) < 16:
            raise ValueError("PRICING_ADMIN_TOKEN must contain at least 16 characters")
        self.mealie, self.queue = mealie, queue
        self.owner = PricingOwner(self.config.data_dir)
        try:
            self.state = PricingState(self.config.data_dir)
            self.store = CatalogStore(self.config.data_dir)
            self.source = MercadonaClient(
                http,
                delay_seconds=self.config.request_delay_seconds,
                max_products=self.config.max_products,
            )
            self.selector = selector or ProductSelector(
                settings.decisions.model_copy(update={"enabled": True})
            )
            interval = self.config.sync_interval_hours * 3600
            scope = "mercadona:" + self.config.postal_code
            if self.state.data.get("scope") != scope:
                self.state.data.update(scope=scope, next_run=time.time(), pending_refresh=True)
            elif self.state.data.get("interval_seconds") != interval:
                self.state.data["next_run"] = time.time() + interval
            self.state.data["interval_seconds"] = interval
            if self.state.data["next_run"] is None:
                self.state.data["next_run"] = time.time()
            active = self.store.load("mercadona", self.config.postal_code)
            if active is not None:
                self.state.data.update(
                    fingerprint=active.fingerprint,
                    warehouse=active.warehouse,
                    product_count=len(active.products),
                    observed_at=active.observed_at,
                )
                if self.state.data.get("valued_fingerprint") != active.fingerprint:
                    self.state.data["pending_refresh"] = True
            self.state.save()
        except BaseException:
            self.owner.close()
            raise
        self._job_lock = asyncio.Lock()
        self._catalog_lock = asyncio.Lock()
        self._job: asyncio.Task[None] | None = None
        self._scheduler: asyncio.Task[None] | None = None
        self._closed = False

    def start(self) -> None:
        if self.config.auto_sync:
            self._scheduler = asyncio.create_task(self._schedule())

    async def _schedule(self) -> None:
        while True:
            now = time.time()
            if self._job is None or self._job.done():
                if now >= self.state.data["next_run"]:
                    self.trigger("scheduled")
                elif self.state.data["pending_refresh"] and now >= self.state.data.get(
                    "refresh_retry_at", 0
                ):
                    self.trigger("refresh")
            await asyncio.sleep(10)

    def trigger(self, kind: str, *, force: bool = False) -> bool:
        if self._job_lock.locked() or (self._job is not None and not self._job.done()):
            return False
        self._job = asyncio.create_task(
            self.refresh(force=force)
            if kind == "refresh"
            else self.sync(manual=kind != "scheduled")
        )
        return True

    async def sync(self, *, manual: bool = True) -> None:
        async with self._job_lock:
            self.state.data.update(running=True, phase="downloading", last_attempt=time.time())
            if not manual:
                self.state.data["next_run"] = time.time() + self.config.sync_interval_hours * 3600
            self.state.save()
            try:
                snapshot = await self.source.download(self.config.postal_code)
                # Persist intent before the manifest can become active, including crash windows.
                self.state.data["pending_refresh"] = True
                self.state.save()
                fingerprint = await self._publish_snapshot(snapshot)
                self.state.data.update(
                    last_success=time.time(),
                    last_error=None,
                    fingerprint=fingerprint,
                    warehouse=snapshot.warehouse,
                    product_count=len(snapshot.products),
                    observed_at=snapshot.observed_at,
                    pending_refresh=True,
                )
                self.state.save()
                await self._refresh_all()
            except asyncio.CancelledError:
                self.state.data.update(phase="interrupted", last_error="interrupted")
                raise
            except Exception as error:
                self.state.data.update(phase="error", last_error=type(error).__name__)
                logger.warning("Pricing sync failed type=%s", type(error).__name__)
            finally:
                self.state.data["running"] = False
                self.state.save()

    async def refresh(self, *, force: bool = False) -> None:
        async with self._job_lock:
            self.state.data.update(running=True, pending_refresh=True)
            self.state.save()
            try:
                await self._refresh_all(force=force)
            except asyncio.CancelledError:
                self.state.data.update(phase="interrupted", last_error="interrupted")
                raise
            except Exception as error:
                self.state.data.update(phase="error", last_error=type(error).__name__)
                logger.warning("Pricing refresh failed type=%s", type(error).__name__)
            finally:
                self.state.data["running"] = False
                self.state.save()

    async def _refresh_all(self, *, force: bool = False) -> None:
        generation = self.state.data.get("refresh_generation", 0)
        self.state.data["phase"] = "refreshing"
        self.state.save()
        processed = failed = 0
        budget = [self.config.max_decisions_per_run]
        scopes: list[str | None] = [None] if self.settings.mealie.api_token else []
        scopes.extend(
            key.removeprefix("MEALIE_API_TOKEN_") for key in self.settings.token_overrides
        )
        for scope in scopes:
            slugs = await self.mealie.get_all_recipes(household_id=scope)
            for slug in slugs:

                async def price_recipe(slug: str = slug, scope: str | None = scope) -> None:
                    await self.process_slug(slug, scope, force=force, budget=budget)

                try:
                    await self.queue.run_now(slug, price_recipe)
                    processed += 1
                except Exception as error:
                    failed += 1
                    logger.warning("Recipe pricing failed type=%s", type(error).__name__)
        pending = bool(failed) or self.state.data.get("refresh_generation", 0) != generation
        self.state.data.update(
            phase="partial" if pending else "idle",
            refreshed=processed,
            refresh_failed=failed,
            pending_refresh=pending,
            refresh_retry_at=time.time() + 300,
            decisions_remaining=budget[0],
        )
        if not pending:
            active = await asyncio.to_thread(self.store.load, "mercadona", self.config.postal_code)
            self.state.data["valued_fingerprint"] = active.fingerprint if active else None
        self.state.save()

    async def _publish_snapshot(self, snapshot: Snapshot) -> str:
        async with self._catalog_lock:
            publication = asyncio.create_task(asyncio.to_thread(self.store.publish, snapshot))
            try:
                return await asyncio.shield(publication)
            except asyncio.CancelledError:
                # Cancellation cannot stop a Python worker thread. Keep ownership until it exits.
                with suppress(Exception):
                    await publication
                raise

    async def _catalog_inputs(
        self, recipe: MealieRecipe
    ) -> tuple[Snapshot | None, list[tuple[str, list[Product]]]]:
        async with self._catalog_lock:
            snapshot = await asyncio.to_thread(
                self.store.load, "mercadona", self.config.postal_code
            )
            inputs: list[tuple[str, list[Product]]] = []
            for ingredient in recipe.recipe_ingredient:
                name = (
                    (ingredient.food.name if ingredient.food else "")
                    or ingredient.original_text
                    or ingredient.display
                )
                candidates = (
                    await asyncio.to_thread(
                        self.store.search,
                        "mercadona",
                        self.config.postal_code,
                        name,
                        self.config.max_candidates + 1,
                    )
                    if snapshot is not None and name.strip()
                    else []
                )
                inputs.append((name, [p for p in candidates if p.available]))
            return snapshot, inputs

    async def _current_recipe(self, original: MealieRecipe) -> MealieRecipe:
        current = await self.mealie.get_recipe(original.slug, get_recipe_household_id(original))
        if _hash(_recipe_input(current)) != _hash(_recipe_input(original)):
            raise PricingDeferred("Recipe inputs changed during pricing")
        return current

    async def process_slug(
        self,
        slug: str,
        household_id: str | None = None,
        *,
        force: bool = False,
        budget: list[int] | None = None,
    ) -> None:
        if self._closed:
            return
        try:
            recipe = await self.mealie.get_recipe(slug, household_id)
            await self.process_recipe(recipe, force=force, budget=budget)
        except Exception, asyncio.CancelledError:
            retry_at = time.time() + 300
            if self.state.data["pending_refresh"]:
                retry_at = min(self.state.data.get("refresh_retry_at", retry_at), retry_at)
            self.state.data.update(
                pending_refresh=True,
                refresh_retry_at=retry_at,
                refresh_generation=self.state.data.get("refresh_generation", 0) + 1,
            )
            self.state.save()
            raise

    async def process_recipe(
        self, recipe: MealieRecipe, *, force: bool = False, budget: list[int] | None = None
    ) -> None:
        snapshot, catalog_inputs = await self._catalog_inputs(recipe)
        selections: list[Product | None] = []
        decision_details: list[dict[str, Any]] = []
        budget = budget if budget is not None else [self.config.max_decisions_per_run]
        cache = self.state.data["selections"]
        extra = recipe.model_extra or {}
        context = _recipe_input(recipe)
        for ingredient, (name, candidates) in zip(
            recipe.recipe_ingredient, catalog_inputs, strict=True
        ):
            selected: Product | None = None
            status, confidence = "not_found", None
            if len(candidates) > self.config.max_candidates:
                status = "too_many_candidates"
            elif (
                len(candidates) == 1
                and normalize_name(candidates[0].name) == normalize_name(name)
                and not any(
                    (
                        ingredient.note,
                        ingredient.display,
                        ingredient.original_text,
                        extra.get("recipeInstructions"),
                        extra.get("description"),
                    )
                )
            ):
                selected, status = candidates[0], "unique_candidate"
            elif candidates:
                key = _hash(
                    {
                        "scope": self.state.data["scope"],
                        "context": context,
                        "ingredient": ingredient.model_dump(mode="json", exclude={"reference_id"}),
                        "candidates": sorted(
                            (p.evidence() for p in candidates), key=lambda p: p["id"]
                        ),
                        "policy": self.selector.signature,
                    }
                )
                saved = None if force else cache.get(key)
                if saved is None and budget[0] > 0:
                    budget[0] -= 1
                    choice = await self.selector.choose(
                        recipe, ingredient, candidates, raise_transient=True
                    )
                    saved = {"id": choice[0], "confidence": choice[1]} if choice else {"id": None}
                    cache[key] = saved
                    while len(cache) > 10000:
                        cache.pop(next(iter(cache)))
                    self.state.save()
                if saved is not None:
                    selected = next((p for p in candidates if p.id == saved["id"]), None)
                    confidence = saved.get("confidence")
                    status = "decisions" if selected else "needs_context"
                else:
                    status = "decision_budget_exhausted"
            selections.append(selected)
            decision_details.append({"status": status, "confidence": confidence})
        result = calculate_costs(recipe, selections)
        result.update(
            retailer="mercadona",
            postal_code=self.config.postal_code,
            currency="EUR",
            catalog_fingerprint=snapshot.fingerprint if snapshot else None,
            warehouse=snapshot.warehouse if snapshot else None,
            prices_observed_at=snapshot.observed_at if snapshot else None,
            policy=self.selector.signature,
            decisions=decision_details,
        )
        for line, product in zip(result["lines"], selections, strict=True):
            if product:
                line["product_url"] = product.url
        names = []
        if result["per_serving_cost"] is not None:
            names.append("Mercadona:" + self._money(result["per_serving_cost"]) + " €/ración")
        if result["purchase_cost"] is not None:
            names.append("Mercadona:" + self._money(result["purchase_cost"]) + " € compra")
        deferred = any(item["status"] == "decision_budget_exhausted" for item in decision_details)
        recipe = await self._current_recipe(recipe)
        metadata = _metadata(recipe)
        previous = metadata["retailers"].get("mercadona", {})
        old_slugs = set(previous.get("managed_tag_slugs", []))
        existing_names = {tag.name for tag in recipe.tags or [] if tag.slug in old_slugs}
        if {
            key: val for key, val in previous.items() if key != "managed_tag_slugs"
        } == result and existing_names == set(names):
            if deferred:
                raise PricingDeferred("Decisions budget exhausted")
            return
        tags = (
            await self.mealie.get_or_create_tags(names, get_recipe_household_id(recipe))
            if names
            else []
        )
        if {tag.name for tag in tags} != set(names):
            raise RuntimeError("Pricing tags unavailable")
        recipe = await self._current_recipe(recipe)
        metadata = _metadata(recipe)
        previous = metadata["retailers"].get("mercadona", {})
        old_slugs = set(previous.get("managed_tag_slugs", []))
        result["managed_tag_slugs"] = [tag.slug for tag in tags]
        metadata["retailers"]["mercadona"] = result
        new_slugs = {tag.slug for tag in tags}
        merged_tags = [
            tag for tag in recipe.tags or [] if tag.slug not in old_slugs | new_slugs
        ] + tags
        patch = MealieRecipePatch(
            tags=merged_tags,
            extras={
                **(recipe.extras or {}),
                PRICING_EXTRA: json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            },
        )
        await self.mealie.patch_recipe(recipe.slug, patch, get_recipe_household_id(recipe))
        verified = await self.mealie.get_recipe(recipe.slug, get_recipe_household_id(recipe))
        if _metadata(verified) != metadata or not set(names).issubset(
            {tag.name for tag in verified.tags or []}
        ):
            raise RuntimeError("Pricing write verification failed")
        if deferred:
            raise PricingDeferred("Decisions budget exhausted")

    @staticmethod
    def _money(value: str) -> str:
        return format(Decimal(value), ".2f").replace(".", ",")

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "retailer": "mercadona",
            "postal_code": self.config.postal_code,
            "sync_interval_hours": self.config.sync_interval_hours,
            "auto_sync": self.config.auto_sync,
            **{key: value for key, value in self.state.data.items() if key != "selections"},
        }

    async def close(self) -> None:
        self._closed = True
        try:
            for task in (self._scheduler, self._job):
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            await self.selector.close()
        finally:
            self.owner.close()
