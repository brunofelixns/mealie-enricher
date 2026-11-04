# Supermarket pricing implementation plan

> **For agentic workers:** Use superpowers:executing-plans for integration and superpowers:dispatching-parallel-agents for the independent importer and calculation tasks. Track progress below.

**Goal:** Import Mercadona for configurable postal code 27004 into a local DuckDB catalog and enrich recipes with exact cost tags and product details.

**Architecture:** An opt-in pricing service owns immutable DuckDB snapshots, persistent scheduling and resolution state, a scoped Mercadona client, and a bounded Decisions selector. Pricing writes are independent of nutrition hashes and serialized through the existing recipe queue. One active pricing process per data directory is enforced with an OS file lock.

**Tech Stack:** Existing Python 3.14, FastAPI, HTTPX, OpenAI SDK, DuckDB and Pydantic; standard-library file locks and atomic JSON metadata. No new runtime dependency.

**Spec:** ../specs/2026-11-03-supermarket-pricing-design.md

## Global constraints

- Preserve all pre-existing uncommitted NOVA/PostgreSQL changes. Work in this checkout to include them; do not stage, commit or publish unrelated work.
- User approved implementation and reuse of the existing OpenAI key. Do not print or persist its value.
- Pricing disabled by default. Initial postal code 27004; weekly means an interval of 168 hours, configurable without code. Manual sync does not move an existing schedule.
- Fixed package arithmetic uses Decimal; unknown quantities/prices remain unknown, never zero. Do not equate volume and mass.
- Exact labels: Mercadona:1,50 €/ración and Mercadona:10,80 € compra. Preserve foreign extras and tags; never delete shared global tags.
- No checkout, payment, production deployment or automatic production data migration.
- Direct API preflight on 2026-11-03: postal-code retrieval 204, scope selection 200 with warehouse 4450, categories and one product 200. This is not a complete-catalog validation.

## Review focus

- New competing products and changed prices invalidate choices; observation timestamps alone do not.
- Missing servings only suppress the per-serving amount; missing ingredient conversions suppress complete totals.
- A failed import or cancelled task preserves the last valid snapshot and scope.
- Pricing runs on unchanged/manual-nutrition recipes without overwriting nutrition.
- Status and manual writes must not expose keys or inherit permissive wildcard CORS access from legacy routes.

## Shared contracts

New package `mealie_enricher.pricing`:

- `models.Product`: id, name, retailer='mercadona', brand, url, category, package_quantity: Decimal|None, package_unit: 'g'|'ml'|'unit'|None, price: Decimal|None, available, variable_weight, drained_quantity: Decimal|None, ingredients, nutrition: dict, raw: dict. `evidence()` returns stable selector data, excluding raw acquisition metadata.
- `models.Snapshot`: retailer, postal_code, warehouse, observed_at (UTC ISO), fingerprint, products: list[Product].
- `store.CatalogStore(directory: str)`: `publish(snapshot: Snapshot) -> str`, `load(retailer: str, postal_code: str) -> Snapshot|None`, `search(retailer: str, postal_code: str, name: str, limit: int=12) -> list[Product]`. Calls are sync and dispatched to a worker thread by integration. Snapshots are immutable files; the manifest activates only complete snapshots. No open reader file is overwritten.
- `mercadona.MercadonaClient(http: httpx.AsyncClient, delay_seconds: float=2, max_products: int=10000)`: `async download(postal_code: str) -> Snapshot`. Fresh isolated cookie scope, verify returned CP and warehouse, bind warehouse to every GET. Reject incomplete/blocked/invalid responses. Product details may omit numeric nutrition.
- `costs.ingredient_quantity(ingredient: MealieIngredient) -> tuple[Decimal|None, str|None]`; `costs.recipe_servings(recipe: MealieRecipe) -> Decimal|None`; `costs.calculate_costs(recipe: MealieRecipe, selections: list[Product|None]) -> dict[str, Any]`. Returns JSON-compatible decimal strings: total_cost, per_serving_cost, purchase_cost (null unless complete), known_total_cost, servings, complete, lines, purchases, unresolved. Line order follows recipe ingredients; identical products group before package rounding.
- `selection.ProductSelector(settings: DecisionSettings, client: AsyncOpenAI|None=None)`: `.signature: str`, `async choose(recipe: MealieRecipe, ingredient: MealieIngredient, candidates: list[Product]) -> tuple[str,float]|None`, `async close()`. Restrict choice IDs, needs_context fallback, validate finite confidence, bounded requests, no generated prices.

## Tasks

### Task 1: Contracts and configuration

- [x] Write model/config tests; confirm failure before implementation.
- [x] Add pricing models and typed settings, including positive finite sync interval, delay, candidate and product limits, admin token and catalog data directory.
- [x] Validate opt-in requires an existing Decisions key and control token, without requiring nutrition Decisions to be enabled.
- [x] Run targeted tests and lint.

### Task 2: Mercadona acquisition and local catalog

Files: `pricing/mercadona.py`, `pricing/store.py`, `tests/integration/test_pricing_catalog.py`.

- [x] Test postal/warehouse scope, product fields, malformed/partial catalog failure and old snapshot preservation; watch failure first.
- [x] Implement complete traversal, request pacing and bounded transient retries. Honor missing/invalid data without silent fallback to a different warehouse.
- [x] Persist products and raw details in DuckDB with dated observations and immutable versions; search by normalized terms locally.
- [x] Test independent scopes, new competitor visibility and safe publication/restart.

### Task 3: Deterministic costs and bounded Decisions choice

Files: `pricing/costs.py`, `pricing/selection.py`, `tests/unit/test_pricing_costs.py`, `tests/integration/test_pricing_selection.py`.

- [x] Write tests for exact decimals, grouped packages, partial results, missing servings, safe units and invalid Decisions responses; watch failure first.
- [x] Implement typed package conversions and arithmetic; do not use legacy volume-as-mass approximations.
- [x] Implement composition/value rubric within ingredient equivalence; abstain for incompatible or insufficient candidates.
- [x] Validate stable evidence excludes timestamps and includes price and composition.

### Task 4: Scheduling, recipe writes and HTTP controls

Files: `pricing/service.py`, `pricing/state.py`, `routes/pricing.py`, `app.py`, `services/processing.py`, `clients/mealie.py`, integration tests.

- [x] Test disabled compatibility, persistent due time/manual updates, import failure, exclusive writer and interruption state.
- [x] Build durable JSON state and OS process lock; one pricing owner per directory. Schedule starts on boot if no valid catalog, remains independent of manual sync, and records outcomes.
- [x] Use local search plus stable per-ingredient cache, with candidates and policy in signature. Revalue on changed relevant inputs, including manual-nutrition and unchanged-hash recipes.
- [x] Fetch current recipe under queue serialization; merge only module-owned tags/extras, verify pricing writes, and isolate errors from nutrition.
- [x] Add protected status/sync/refresh endpoints. All pricing requests require a dedicated constant-time-checked bearer token; cross-origin requests are rejected.

### Task 5: Documentation, deployment examples and validation

- [x] Document feature status, configuration, protected manual controls, interval semantics, partial costs, stale data and limitations.
- [x] Add settings to both environment examples and both Compose files without altering PostgreSQL/NOVA work.
- [x] Run targeted suite, full existing suite, Ruff format/check, mypy and Compose config checks.
- [x] Validate one real scoped product with the implemented adapter; do not claim complete-catalog validation from a sample.
- [x] Request one independent implementation review, resolve material findings, then report local vs live evidence and remaining limits.

## Execution ledger

- Implementation authorized by user after proposal review; reuse existing key explicitly approved. No new key setup.
- Default decision: interval scheduling (168 hours) rather than inventing a weekly day/time; configurable through project settings. Purchase assumes no pantry and excludes delivery. No medical scoring or fixed manual overrides in first version.
- Preserve current dirty checkout: no worktree created from HEAD because it would omit the uncommitted integrations this feature extends. No commits or publication requested.

## Final verification and review

- Full current checkout: `747 passed, 37 skipped` (127.53 s). Opt-in Docker checks are not included in this default count.
- Isolated Mealie pricing E2E plus service regressions: `15 passed` (25.31 s), including exact Unicode price tag names, replacement, JSON extras and unchanged manual calories.
- Real Mercadona sample: postal code 27004, warehouse 4450, product 10005, 1000 ml, EUR 2.45. DuckDB search returned that ID; deterministic sample costs EUR 0.49 total, EUR 0.25/serving, EUR 2.45 purchase.
- Real Decisions call selected product 10005 with confidence 0.96. This is one provider smoke check, not a quality benchmark or complete catalog import.
- Ruff check/format, `git diff --check`, mypy (60 source files) and both Compose configuration checks passed. Published Compose used an ignored temporary env-file override with the sample variables because no operator `.env` exists.
- Independent review found seven important issues; each was fixed with regression evidence: concurrent personal edits; catalog version consistency; draining publication before releasing ownership; restart reconciliation; preparation-aware single-candidate handling; resuming budget-limited batches; transient provider failure recovery.
- Live probes additionally exposed the exact postal retrieval action path, nullable available-product status and Mealie-generated reference IDs. Regressions pin these observed behaviors.
- No code or data deployed to the user's Mealie, no release published, and no unrelated changes committed. Feature remains opt-in. Complete catalog validation was subsequently requested and is recorded below.

## Complete Mercadona catalog validation, 2026-11-03

- User explicitly requested the full download for 27004, DuckDB persistence/search validation, and corrections for any observed failures.
- First real traversal failed on product ID `81649.1`. Category IDs remain numeric; product IDs now preserve the source's optional numeric variant suffix. A regression failed before the correction, then the catalog suite passed: `48 passed`, including unsafe-ID rejection and distinct variants after a DuckDB round trip.
- Successful fresh download: 4,291 unique listed IDs = 4,291 successful product-detail IDs = 4,291 snapshot products = 4,291 DuckDB rows and price observations. Scope: Mercadona, postal code 27004, warehouse 4450. There are 54 variant IDs, all preserved; the completed run had no HTTP errors.
- Live calls: 153 category requests, 4,291 product requests, two postal-scope requests. Single sequential acquisition with 0.25-second minimum request spacing; production default remains two seconds. Download took 1,172.69 seconds; publication plus verification completed in 1,222.19 seconds.
- DuckDB size: 25,440,256 bytes. All products have a price. 3,203 have normalized package quantities; 2,705 have ingredients; 386 are variable weight. Ambiguous/missing data stays unknown and raw details are retained.
- Manifest fingerprint: `cae4ad9b53a09961fffc63476648982ce4ab76d705cc569d9d6ad835f042e251`. All product fields survived reload. A separate fresh process with socket connections blocked loaded the immutable file, checked raw IDs and exact decimal columns against JSON, and searched arroz/leche/tomate/garbanzos/aceite oliva/salmón, including accent normalization and scope isolation.
- Ignored local evidence: `.cache/mercadona-27004-full/latest-report.json`, `offline-report.json`, `catalog/mercadona-27004.json`, its referenced DuckDB, and timestamped response captures. No production catalog or Mealie installation changed.
- Full regression suite after the fix: `757 passed, 37 skipped` in 118.18 seconds. Ruff check/format, mypy (60 source files), and `git diff --check` passed. No new Mealie E2E run was necessary for this acquisition-only change; previous isolated Mealie evidence remains separate.

## Implementation decisions

- Weekly scheduling uses a configurable interval of 168 hours. It does not assume a calendar day/time that the user had not chosen.
- Local process ownership is enforced per pricing data directory. Recipe candidate reads block manifest publication only while collecting candidates; provider calls can proceed after the immutable inputs are captured.
- A successful catalog activation and recipe valuation are separate durable states. Interrupted/pending work is resumed, including a bounded next batch after budget exhaustion.
- Semantic abstentions are cached until changed inputs or a forced refresh; network/timeout/429/5xx failures are retryable and never cached as permanent abstentions.
- Optimistic rereads preserve remote edits made during selection. The upstream API offers no conditional versioned patch in this client, so a final read-to-write race remains a documented boundary.
- Unknown weights, conversions, variable-weight packages and absent prices remain pending. Shipping, pantry accounting and fixed manual product overrides are outside the initial implementation.
