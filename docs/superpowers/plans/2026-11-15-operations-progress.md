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
