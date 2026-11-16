# Operations and progress implementation plan

> For agentic workers: use superpowers:executing-plans for inline implementation.

**Goal:** Show real Mercadona download progress and expose existing application controls in the web view.

**Architecture:** Add an optional acquisition callback and a small persistent progress tracker. Reuse existing FastAPI controls and Jinja view, with same-origin authenticated pricing requests.

**Tech Stack:** Python 3.14, FastAPI, httpx, Jinja, vanilla JavaScript, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-operations-progress-design.md`

## Global constraints

- No new frontend dependency; preserve Mealie theme and history.
- No embedded or browser-persisted administrative token; retain cross-origin rejection.
- Keep atomic catalog publication and existing API contracts.
- No deployment, real catalog download or paid provider calls during tests.

## Review focus

- Unknown totals and interruptions must not look complete.
- Polling failure must preserve the last observed data and identify stale state.
- Concurrent commands must not start duplicate pricing jobs.
- Same-origin checks must reject foreign or malformed Origins.
- Missing or incorrect tokens must not trigger protected operations.

### Task 1: Real progress and protected endpoint

Files: `pricing/mercadona.py`, new `pricing/progress.py`, `pricing/service.py`, `routes/pricing.py`; integration tests for acquisition, progress and Origin handling.

Interfaces: optional synchronous acquisition callback `(stage, completed, total, current)`; `PricingService.progress_status()` returns safe progress data; `GET /pricing/progress` uses existing Bearer authentication.

- [x] Write tests observing one of two downloaded products, durable counters and auth/origin behavior.
- [x] Verify the regression against the original HEAD acquisition module: missing callback fails with TypeError.
- [x] Implement callback, checkpointed counters, periodic logs and endpoint.
- [x] Run focused pricing tests and inspect output.

### Task 2: Operations in the existing view

Files: `templates/history.html`, new operations template/scripts, `routes/history.py`, view/browser tests and documentation.

Interfaces: existing GET/POST routes and the new progress endpoint; token held only in page memory.

- [x] Replace the intentionally obsolete byte-for-byte HTML assertion with rendered-view contract checks.
- [x] Implement forms, read controls, asynchronous feedback and progress polling.
- [x] Verify rendered forms and JavaScript behavior.
- [ ] Verify the desktop/mobile view visually: local browser connections are blocked by the execution environment.
- [x] Run suite, lint/type checks, review final diff and record evidence below.

## Execution record

## Follow-up: explicit recipe refresh and Mercadona flow verification (2026-11-16)

- User requests a dedicated forced recipe-update endpoint and visible recipe-update progress, followed by verification that Mercadona is wired into the whole processing flow. Continue the existing PR #25, head `e24ad83524d4fb9601d7e73d17f394d94b0d2584`.
- Existing integration is present in `ProcessingService._process` finally: pricing runs for webhook, estimate and backfill, including manual calories/unchanged/filtered nutrition. Synchronization calls `_refresh_all` after catalog publication.
- Add authenticated `POST /pricing/recipes/refresh`: force the recipe review with the current catalog, coalesce concurrent jobs, reject missing catalog with 409. Preserve existing refresh API.
- Add independent recipe counters (reviewed, succeeded, failed, total, current, running and finish time) to protected progress and expose them in the web panel, with a dedicated force-update button.
- Reproduce/fix missing-catalog processing writing empty results and failed/interrupted initial sync recovery not retrying acquisition. Preserve old recipe data and valid catalog; use bounded retry timing and a pending-sync flag.
- Verify all pricing tests plus processing integration and client tests; update the same PR through the GitHub connector because local Git metadata is read-only and gh auth is expired.
- Initial PR CI is green for full CI, security and CI/dependency quality; optional real Mealie pricing tests ran in CI. This does not verify the user's live deployment or paid model calls.
- Read-only production audit (2026-11-16): deployed version 1.3.0, idle, no last error, 4,287 catalog products, warehouse 4450, 563 reviewed recipes, zero technical review errors, no pending refresh. Mealie currently lists 566 recipes. Three sampled recipes all contain catalog-linked pricing metadata but incomplete totals: one has one matched product of two and missing quantity/product; the others have zero matches of six and thirteen lines. This proves integration and acquisition, not satisfactory overall selection quality. No production writes, syncs or paid calls were made.
- Offline search reproduction using the previously downloaded full catalog: `Media taza de quinoa` and `100 gramo(s) Quinoa` return no candidates; `quinoa` returns two. Added recovery of food name for search only, retaining source ingredients and the structured-quantity costing policy. Both originalText/display regressions failed before the fix and passed afterward.
- Added regression coverage for all three real HTTP entrypoints, forced review/cache bypass, concurrent requests, missing-catalog preservation, acquisition retry, incomplete-price counts and interrupted nested progress. Scoped integration/unit verification before final search change: 269 passed, one optional test skipped. Client tests: seven passed; mypy: 61 source files without issues.
- Independent follow-up review found a bounded-force bug: after exhausting its budget, a retry reused old cached decisions for the remaining ingredients. A two-ingredient regression reproduced the wrong second product. Forced batches now clear saved choices once and persist this before processing, then use ordinary caching so retries reuse only new decisions. The regression passes and the reviewer reports no remaining blockers. Final focused recipe/service run: 32 passed.
- Final full-suite verification after all Python changes: **832 passed, 37 skipped**, 350.98 seconds, using the same ignored socketless harness. All seven client tests pass after the final wording adjustment. Ruff check and format check (143 files), mypy (61 source files), JavaScript syntax and whitespace checks pass. Optional live/container checks are skipped locally; no production sync or paid calls were triggered.
- Delivery continues PR #25 through the GitHub connector, preserving the original PR commit as parent. Publishing an image and deploying are separate from this change. Visual desktop/mobile validation remains blocked by local browser connectivity.

## Initial implementation evidence

- Native task service failed twice before changes; implementation proceeded in the current checkout. No deployment was performed.
- Baseline: standard Windows async tests hang in socket.socketpair/accept because localhost is blocked. A traceback in `.cache/loop-trace.txt` identified this before continuing. No production workaround was added.
- Test harness: `.cache/run_inprocess_checks.py` uses a polling event loop without socket I/O. It still executes the real app, ASGI transport, storage and mocked HTTP acquisition; actual socket registration is rejected. The helper is ignored scratch and is not shipped.
- Main Python suite: 817 passed, 37 skipped, 474.61 seconds. Optional live/container tests remain skipped. Two additional progress cases were then included in the targeted run below.
- Focused pricing/catalog/history run: 81 passed. Additional progress/CI run: 58 passed.
- Final progress run: 8 passed, including interruption persistence, message redaction, protected endpoint and observation before download completion.
- Negative regression check: loading the original HEAD Mercadona module in a separate process makes the new download-progress test fail with the expected missing `on_progress` argument. Current code passes it.
- Fresh read-only review found stale protected responses after disconnect and duplicate accepted backfill submissions. Both were reproduced in the JavaScript tests, fixed and verified: 5 client tests passed. CI now runs these tests too.
- A final interruption regression exposed a finish timestamp being overwritten on subsequent restarts; the test failed first, then passed after preserving an existing timestamp.
- Ruff check and format check passed; mypy reported no issues in 61 source files. JavaScript syntax and git diff whitespace checks passed.
- Visual limitation: the preview server started, but both browser surfaces timed out on localhost. No desktop/mobile visual verification or live deployment is claimed.
- Publishing an image and deploying to Dokploy are still required to expose this version on the server. Local Git metadata is read-only in the execution environment; PR submission uses the GitHub connector and leaves the local working files intact.
