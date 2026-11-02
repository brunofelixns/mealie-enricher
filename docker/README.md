# Run the published Docker image

**English** | [Español](README.es.md) | [Project overview](../README.md)

Run Mealie Enricher from **GitHub Container Registry (GHCR)** using Docker with Compose. You do not need Python, uv or a source checkout on the server.

GitHub Actions manages versions automatically and publishes `latest` plus immutable version tags for linux/amd64 and linux/arm64 after the full suite passes. [Workflow, versions and recovery](../docs/16-github-actions.md).

## 1. Configure

Copy [docker-compose.yml](docker-compose.yml) and [.env.example](.env.example) into a server directory. Run the following commands from that directory:

~~~sh
cp .env.example .env
~~~

In PowerShell, use `Copy-Item .env.example .env` instead. Edit at least:

~~~dotenv
MEALIE_ENRICHER_IMAGE=ghcr.io/brunofelixns/mealie-enricher:latest
MEALIE_URL=https://your-mealie.example.com
MEALIE_API_TOKEN=your-mealie-api-token
LLM_ENABLED=false
~~~

Household-specific tokens can be configured using the comments in `.env.example`. Compose loads them through `env_file`; no household IDs need to be added to the YAML.

`PUBLISHED_PORT` is the host port and `PORT` is the container port. For example, `PUBLISHED_PORT=8002` and `PORT=8000` expose the service on host port 8002.

Mealie must be reachable from the container. `localhost` inside the container refers to the container itself. Use your Mealie server URL, or a shared Docker network when connecting services by container name.

The fallback LLM is disabled initially. To enable it, set `LLM_ENABLED=true` and configure the provider URL, model and `LLM_API_KEY`. Decisions has separate settings and is also disabled initially.

## 2. Pull and start

~~~sh
docker compose config --quiet
docker compose pull
docker compose up -d --no-build --wait --wait-timeout 90
docker compose ps
~~~

This Compose uses `image` only; it does not build from source. With `PUBLISHED_PORT=8000`:

- Health: `http://localhost:8000/health`
- Activity: `http://localhost:8000/estimator/history`
- Mealie webhook destination: `http://YOUR-ENRICHER-HOST:8000/webhook`

The webhook must be reachable from Mealie. Adjust external URLs when changing `PUBLISHED_PORT`. The activity page shows processing states, changes, duration, nutrition and errors, and refreshes every two seconds. Automatic recipe tags are currently in Spanish.

Deploy on a trusted network or behind an authenticated reverse proxy: the application preserves upstream HTTP access behavior and has no built-in authentication.

View logs:

~~~sh
docker compose logs -f --tail 100 calorie-estimator
~~~

## Updates and persistence

Set `MEALIE_ENRICHER_IMAGE` to a newly published version, then:

~~~sh
docker compose pull
docker compose up -d --no-build --wait --wait-timeout 90
~~~

`latest` follows releases. For reproducible deployments, use a version tag or pin the manifest digest returned by:

~~~sh
docker buildx imagetools inspect ghcr.io/brunofelixns/mealie-enricher:latest
~~~

The reference format is `ghcr.io/brunofelixns/mealie-enricher@sha256:YOUR_VERIFIED_DIGEST`.

The `estimator-cache` volume preserves `/app/data/cache.db`. Keep `CACHE_DB_PATH=/app/data/cache.db` and the same Compose project name to reuse it.

Stop with `docker compose down`. This preserves volumes. History and pending tasks are in memory and are lost on restart; run a single application instance.

## Included BEDCA catalog

From **1.2.0**, `latest` and normal version tags include the prepared DuckDB
catalog and original CSV files under `/opt/bedca`, with BEDCA's non-commercial
terms and attribution. The standard [.env.example](.env.example) enables the
included catalog. [Contents and updates, in Spanish](../docs/15-imagen-con-bedca.md).

Keep `CATALOG_ENABLED=true` and `CATALOG_DB_PATH=/opt/bedca/catalogos.duckdb`.
Existing `bedca` and `latest-bedca` aliases point to the same complete image;
new releases do not publish a separate version-bedca variant.

For a custom export instead, place your separately obtained `bedca_foods.csv`,
`bedca_foodvalues.csv` and `bedca_units.csv` in `bedca/`, or set `BEDCA_INPUT_DIR`.
Set `BEDCA_DATASET_VERSION` to identify the export.

~~~sh
docker compose --profile catalog run --rm catalog-import
~~~

After a custom import, set `CATALOG_ENABLED=true` and
`CATALOG_DB_PATH=/app/catalogs/catalogos.duckdb` in `.env` and recreate the service.
The custom catalog lives in `estimator-catalogs`, mounted read-only. The cache
remains in its own writable volume.

Optional Decisions match selection requires `DECISIONS_ENABLED=true` and `OPENAI_API_KEY` or `DECISIONS_API_KEY`. The fallback LLM remains independent.

[Catalog preparation and safe updates, in Spanish](../docs/11-catalogos-duckdb.md).

## Release and publication recovery

Main requires pull requests and passing CI. Release Please maintains the version
and changelog PR; merging it creates the release and requests the tested images.
Do not edit version numbers or overwrite versioned image tags manually.

If publication fails, use **Re-run failed jobs**. A maintainer can also request
validation/publication of a tag created by the current Release Please flow:

~~~sh
gh workflow run ci-release.yml --repo brunofelixns/mealie-enricher --ref main -f release_tag=vX.Y.Z
~~~

An older release retry preserves the latest image aliases. The workflow checks
the exact merged release PR, tag and metadata, runs the full suite, then builds
and verifies the complete image on both architectures. Historical dual-image
releases retain their recovery contract. No manual registry token is needed.

[CI and release policy, in Spanish](../docs/16-github-actions.md).
