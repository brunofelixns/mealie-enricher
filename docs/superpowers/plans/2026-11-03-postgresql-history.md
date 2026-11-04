# PostgreSQL and Persistent History Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement the tasks inline with TDD and a final independent review.

**Goal:** Support PostgreSQL for runtime data and retain execution history across restarts.

**Architecture:** A shared SQLAlchemy async engine runs Alembic migrations and serves cache/history stores. Preserve the synchronous execution-handle interface; explicitly await history flushes at processing boundaries and before history reads. Compose provisions PostgreSQL 18.

**Tech Stack:** Python 3.14, SQLAlchemy 2, psycopg 3, Alembic, PostgreSQL 18, pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-postgresql-history.md`

## Global Constraints

- Preserve uncommitted NOVA changes and existing HTTP/nutrition behavior.
- BEDCA remains read-only DuckDB; application coordination remains single-process.
- No deployment, publication, or automatic retry of interrupted Mealie writes.
- Explicit DATABASE_URL enables durable history; absent URL preserves legacy behavior.
- PostgreSQL credentials must not appear in application logs or configuration repr.

## Review Focus

- Completion after an execution leaves the in-memory page must still persist.
- Database errors must fail visibly rather than silently losing history.
- Retention must not delete running jobs or apply the legacy 24-hour expiration.
- Database URLs with special password characters must work in Compose.
- New migrations must preserve all legacy SQLite rows and support PostgreSQL.

## Task 1: Database configuration and dialect-independent cache

- [x] Add failing configuration and backend cache round-trip tests.
- [x] Add psycopg, async Alembic connection support and dialect-specific upserts.
- [x] Verify SQLite migration compatibility and PostgreSQL cache behavior.

Files: `config.py`, `storage/database.py`, `storage/cache.py`, `alembic/env.py`,
`alembic/versions`, `pyproject.toml`, `uv.lock`, `tests/unit/test_database_config.py`,
`tests/integration/test_database.py`.

## Task 2: Persistent history and lifecycle integration

- [x] Add failing restart, pagination, retention and interrupted-execution tests.
- [x] Implement SQL history, explicit flushes and application lifecycle integration.
- [x] Verify existing history, processing and NOVA behavior.

Files: `storage/schema.py`, `storage/history.py`, `storage/sql_history.py`,
`services/processing.py`, `routes/history.py`, `app.py`, database integration tests.

## Task 3: Compose, documentation and complete verification

- [x] Configure PostgreSQL service, volume, healthcheck and safe credentials in both Compose files.
- [x] Document configuration, updates, backups, retention and single-instance limits in English/Spanish.
- [x] Run real PostgreSQL tests, complete ordinary suite, Ruff, formatting, mypy and Compose validation.
- [x] Obtain independent review and address material findings with regression tests.

## Execution notes

- Work in place to preserve the user's uncommitted feature; no commits or worktree copy are needed.
- Existing SQLite history unit tests retain their upstream expiry behavior; persistence tests explicitly set DATABASE_URL.
- Final ordinary suite: 581 passed, 28 optional Docker cases skipped, 96.05% coverage;
  PostgreSQL-backed tests ran against PostgreSQL 18 in disposable isolated schemas.
- Separate deployment Compose E2E: 1 passed; special-character password preserved,
  execution history unchanged after recreating both application and PostgreSQL.
- Independent review found missing polling deltas and cleanup after SQL failure;
  four regression tests reproduced both findings and then passed after fixes.
- Ruff, formatting, mypy, uv lock, Compose validation, actionlint using the existing
  concurrency.queue compatibility filter, and zizmor were checked locally.
- Built local amd64 image `mealie-enricher:postgresql-test` with bundled BEDCA;
  no hosted CI, ARM run, publication or production deployment was performed.
