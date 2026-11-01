# Run the published Docker image

**English** | [Español](README.es.md) | [Project overview](../README.md)

Run Mealie Enricher from **GitHub Container Registry (GHCR)** using Docker with Compose. You do not need Python, uv or a source checkout on the server.

Image: `ghcr.io/brunofelixns/mealie-enricher:1.13.0` (linux/amd64 and linux/arm64). The package is public and does not require registry authentication.

## 1. Configure

Copy [docker-compose.yml](docker-compose.yml) and [.env.example](.env.example) into a server directory. Run the following commands from that directory:

~~~sh
cp .env.example .env
~~~

In PowerShell, use `Copy-Item .env.example .env` instead. Edit at least:

~~~dotenv
MEALIE_ENRICHER_IMAGE=ghcr.io/brunofelixns/mealie-enricher:1.13.0
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
docker buildx imagetools inspect ghcr.io/brunofelixns/mealie-enricher:1.13.0
~~~

The reference format is `ghcr.io/brunofelixns/mealie-enricher@sha256:YOUR_VERIFIED_DIGEST`.

The `estimator-cache` volume preserves `/app/data/cache.db`. Keep `CACHE_DB_PATH=/app/data/cache.db` and the same Compose project name to reuse it.

Stop with `docker compose down`. This preserves volumes. History and pending tasks are in memory and are lost on restart; run a single application instance.

## Optional BEDCA catalog

BEDCA data is not redistributed with the source or image. Place your separately obtained `bedca_foods.csv`, `bedca_foodvalues.csv` and `bedca_units.csv` in `bedca/`, or set `BEDCA_INPUT_DIR`. Set `BEDCA_DATASET_VERSION` to identify the export.

~~~sh
docker compose --profile catalog run --rm catalog-import
~~~

After import, set `CATALOG_ENABLED=true` in `.env` and recreate the service. The catalog lives in `estimator-catalogs`; the application mounts it read-only. The cache remains in its own writable volume.

Optional Decisions match selection requires `DECISIONS_ENABLED=true` and `OPENAI_API_KEY` or `DECISIONS_API_KEY`. The fallback LLM remains independent.

[Catalog preparation and safe updates, in Spanish](../docs/11-catalogos-duckdb.md).

## Build and publish a release locally

Maintainers can publish without GitHub Actions credits. From the repository root, sign in using `docker login ghcr.io -u YOUR_GITHUB_USERNAME` with a GitHub classic personal access token that has `write:packages`. Enter the token at the password prompt; do not put it in a command, file or issue.

Build, test and publish the source revision being released. For example, on PowerShell, after the ordinary suite passes:

~~~powershell
$releaseRevision = git rev-parse HEAD
docker buildx build --platform linux/amd64,linux/arm64 --provenance=false --sbom=false --build-arg VERSION=1.13.0 --build-arg VCS_REF=$releaseRevision --tag ghcr.io/brunofelixns/mealie-enricher:1.13.0 --tag ghcr.io/brunofelixns/mealie-enricher:latest --push .
docker buildx imagetools inspect ghcr.io/brunofelixns/mealie-enricher:1.13.0
~~~

Use a new version for future releases and verify a clean deployment before announcing them. Optional provenance and SBOM attestations are disabled in this command because GHCR rejected the initial publication containing them; source, version and license remain in the image's OCI labels. Package visibility is managed separately from repository visibility; verify that an unauthenticated client can pull the image.

[GHCR documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
