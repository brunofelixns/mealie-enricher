# PostgreSQL and persistent history

Implement the user's requested PostgreSQL integration in the existing checkout,
preserving the uncommitted NOVA work and all nutrition and HTTP contracts.

Use SQLAlchemy with psycopg 3 and Alembic. `DATABASE_URL` selects PostgreSQL or
explicit SQLite persistence. Without it, retain the existing SQLite cache and
ephemeral history behavior for compatibility. Compose defaults to PostgreSQL 18
with a named volume, readiness check and no published database port. BEDCA stays
in its read-only DuckDB catalog.

Persist each execution's start, recipe metadata, result and failure. Retain all
history by default; `HISTORY_RETENTION_DAYS=0` means unlimited. Keep the existing
history JSON list contract, default page size and `since` filter; add bounded
`limit` and `offset` pagination. On startup mark unfinished persisted executions
as interrupted errors. Do not automatically repeat writes to Mealie. The queue
and recipe locks remain single-process and in memory.

Use dialect-specific conflict updates behind one cache interface. Preserve
existing SQLite cache files and migration data. Switching to PostgreSQL starts
with an empty cache; do not delete or silently migrate the old cache.

Validate against SQLite and an isolated real PostgreSQL container, including
restart survival, cache updates, history pagination, retention, interrupted work,
and migrations. Update both Compose files, examples, CI and bilingual deployment
documentation. Do not deploy or publish the user's service.
