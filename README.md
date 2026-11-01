<p align="center">
  <a href="https://docs.mealie.io/"><img src="docs/assets/mealie-logo.png" width="64" height="64" alt="Mealie logo"></a>
</p>

<h1 align="center">Mealie Enricher</h1>

<p align="center">
  <strong>Your recipes, with more information.</strong><br>
  Self-hosted nutrition estimates and automatic tags for your Mealie recipe collection.
</p>

<p align="center">
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.14"></a>
  <a href="src/mealie_enricher/app.py"><img src="https://img.shields.io/badge/FastAPI-API-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://github.com/brunofelixns/mealie-enricher/pkgs/container/mealie-enricher"><img src="https://img.shields.io/badge/GHCR-1.13.0-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker image on GHCR"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-D65108?style=flat-square" alt="GPL 3.0 license"></a>
</p>

<p align="center">
  <strong>English</strong> · <a href="docs/README.es.md">Español</a> · <a href="docs/README.md">Documentación en español</a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> · <a href="#activity-history">Activity history</a> · <a href="docker/README.md">Deployment</a> · <a href="#documentation">Documentation</a> · <a href="CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">
  <img src="docs/assets/mealie-enricher-banner.png" width="100%" alt="Mealie Enricher illustration connecting ingredients, recipes, nutrients and tags">
</p>

## Give your recipes nutritional context

Mealie Enricher runs alongside [Mealie](https://github.com/mealie-recipes/mealie). It receives recipe events, resolves ingredients, and writes estimated nutrition and automatic tags back to the recipe. A small web interface shows each run and its outcome.

It started as a Python migration of [mealie-calorie-estimator 1.12.3](https://github.com/timo-reymann/mealie-calorie-estimator/tree/c2dc71a1d8effe29375391f2fe50da94d27cfd7d), preserving its HTTP contracts and processing rules. Version **1.13.0** adds optional local **DuckDB/BEDCA catalogs** and **OpenAI Decisions** for ambiguous ingredient matches. The original Open Food Facts path remains available with `CATALOG_ENABLED=false`.

| Feature | What you get |
|---|---|
| **Nutrition per serving** | Estimated calories, macronutrients and other available nutrients. |
| **Automatic Spanish tags** | Calorie and digestibility categories visible in Mealie. |
| **Optional AI** | Fallback for unresolved unit weights or nutrients; optional catalog match selection. |
| **Local food catalogs** | Import your own BEDCA export into DuckDB; SQLite stays dedicated to caching. |
| **Visible activity** | Recipe links, status, changes, duration, nutrients and errors. |
| **Less repeated work** | Ingredient hashes, a SQLite cache and event grouping per recipe. |

## Quick start

You need a running Mealie instance, an API token and Docker with Compose. Images are published for **linux/amd64** and **linux/arm64**:

~~~text
ghcr.io/brunofelixns/mealie-enricher:1.13.0
ghcr.io/brunofelixns/mealie-enricher:latest
~~~

The version tag gives you a predictable deployment; `latest` follows future releases. Public images can be pulled without a GitHub account.

Download the deployment files:

~~~sh
mkdir mealie-enricher
cd mealie-enricher
curl -fsSL https://raw.githubusercontent.com/brunofelixns/mealie-enricher/main/docker/docker-compose.yml -o docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/brunofelixns/mealie-enricher/main/docker/.env.example -o .env
~~~

In PowerShell, use `curl.exe` for the downloads. You can also download [docker-compose.yml](docker/docker-compose.yml) and [.env.example](docker/.env.example) manually, saving the latter as `.env`.

Edit these values in `.env`:

~~~dotenv
MEALIE_ENRICHER_IMAGE=ghcr.io/brunofelixns/mealie-enricher:1.13.0
MEALIE_URL=https://your-mealie.example.com
MEALIE_API_TOKEN=your-mealie-api-token
LLM_ENABLED=false
~~~

Start the service:

~~~sh
docker compose config --quiet
docker compose pull
docker compose up -d --no-build --wait --wait-timeout 90
~~~

Open [localhost:8000/estimator/history](http://localhost:8000/estimator/history) to view activity. Configure your Mealie recipe webhook to send events to `http://YOUR-ENRICHER-HOST:8000/webhook`; the event body must include `document_data` as described in the [API contract](docs/03-compatibilidad-y-validacion.md).

`MEALIE_URL` must be reachable from the container, and the webhook must be reachable from Mealie. Inside a container, `localhost` refers to that container. Use a shared Docker network when connecting services by container name.

[Full deployment guide](docker/README.md) · [Guía de despliegue en español](docker/README.es.md)

## Activity history

The web interface at `/estimator/history` lets you:

- Follow recipe processing and open each recipe in Mealie.
- Inspect status, changes, duration, nutrients per serving and errors.
- Filter by event source and state.
- Receive updates every **two seconds**, with light and dark themes.

History defaults to **200 entries**, expires after **24 hours** and is lost when the process restarts. Use `DEV_SEED_HISTORY=true` only for synthetic development activity. The banner above is an illustration, not a screenshot.

## Automatic tags

The application currently writes automatic tags in **Spanish**, regardless of the README language. Personal tags are preserved.

| Calories per serving | Tag |
|---|---|
| Below 350 kcal | **Calorías:Bajas** |
| 350–600 kcal | **Calorías:Moderadas** |
| Above 600, up to 850 kcal | **Calorías:Altas** |
| Above 850 kcal | **Calorías:Muy altas** |

Digestibility tags are `Digestión:Fácil`, `Digestión:Moderada`, `Digestión:Lenta` and `Digestión:Desconocida`, following the original rules. Legacy English tags are replaced when a recipe is processed again. If its ingredient hash has not changed, existing nutrition is reused and only tags and related extras are updated.

[Tags and history, in Spanish](docs/09-etiquetas-y-vista-web.md).

## How it works

~~~mermaid
flowchart LR
    A["Mealie recipe event"] --> B["Per-recipe queue"]
    B --> C["Unit conversion and ingredient resolution"]
    C --> D["Open Food Facts or local DuckDB/BEDCA"]
    C --> E["Optional AI fallback or match selection"]
    D --> F["Python nutrient calculations and tags"]
    E --> F
    F --> G["Update Mealie"]
    G --> H["Activity history"]
~~~

Python performs the nutrient calculations. In catalog mode, Decisions selects food matches and can leave ingredients unresolved when evidence is insufficient. It does not calculate nutrition. The LLM fallback and Decisions are separate, optional settings.

### Optional BEDCA catalog

BEDCA data is **not included** in the repository or image. Obtain the three required CSV exports separately and place them in `bedca/` next to your deployment `.env`:

~~~text
bedca_foods.csv
bedca_foodvalues.csv
bedca_units.csv
~~~

Import them into the catalog volume:

~~~sh
docker compose --profile catalog run --rm catalog-import
~~~

Then set `CATALOG_ENABLED=true` in `.env` and recreate the service. The app mounts the catalog read-only, while its SQLite cache uses a separate writable volume. Set `BEDCA_DATASET_VERSION` to identify your export.

[Catalog preparation and updates, in Spanish](docs/11-catalogos-duckdb.md). Tables for future supermarket products and prices are present; no product datasets or collectors are included.

## Configuration

The deployment [.env.example](docker/.env.example) lists available settings. The [root example](.env.example) supports development and building from source.

| Variable | Purpose |
|---|---|
| `MEALIE_URL` / `MEALIE_API_TOKEN` | Mealie instance and API token. |
| `MEALIE_API_TOKEN_<HOUSEHOLD_ID>` | Optional household-specific token; replace punctuation in the ID with underscores. |
| `LLM_ENABLED` | Enable the optional fallback LLM. |
| `LLM_BASE_URL` / `LLM_ENDPOINT_URL` | Compatible provider URL and endpoint. |
| `LLM_API_KEY` / `LLM_MODEL` | Fallback provider credentials and model. |
| `CATALOG_ENABLED` / `CATALOG_DB_PATH` | Enable a prepared local DuckDB catalog. |
| `DECISIONS_ENABLED` | Enable optional selection of ambiguous catalog matches. |
| `DECISIONS_API_KEY` / `OPENAI_API_KEY` | Decisions credentials; the former takes precedence. |
| `ESTIMATE_STRATEGY` / `ESTIMATE_TAG` | Process all recipes or only those carrying a selected tag. |
| `OFF_LANGUAGE` | Open Food Facts search language. |
| `CACHE_DB_PATH` | SQLite cache; keep `/app/data/cache.db` in Docker. |
| `PORT` / `PUBLISHED_PORT` | Container and host port in the deployment Compose. |

Code defaults retain Mistral and German OFF search from the original application. The Compose examples use an OpenAI-compatible endpoint and English OFF search. Configure your provider and language explicitly. The Agents SDK adapter does not require changing providers.

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Service status and UTC timestamp. |
| POST | `/webhook` | Accept a Mealie event containing `document_data`. |
| POST | `/estimate` | Force estimation for `content.slug`. |
| POST | `/backfill` | Process existing recipes in the background. |
| GET | `/estimator/history` | Open the activity interface. |
| GET | `/estimator/history.json` | Read history; accepts `since` in milliseconds. |

Example body for `POST /estimate`:

~~~json
{"content": {"slug": "my-recipe"}}
~~~

Accepted processing requests return **202**. Check the history for the final result.

## Development

Install **Python 3.14** and **uv**, then:

~~~sh
git clone https://github.com/brunofelixns/mealie-enricher.git
cd mealie-enricher
uv sync --locked
cp .env.example .env
~~~

In PowerShell, replace `cp` with `Copy-Item`. Edit `.env`, then run:

~~~sh
uv run --env-file .env python -m mealie_enricher
~~~

For a local Docker build, use `docker compose up -d --build calorie-estimator` from the repository root. Run **one application process**: its queue, rate limiters and history are in memory.

### Checks

~~~sh
uv run ruff check src tests alembic
uv run ruff format --check src tests alembic
uv run mypy src
uv run pytest
~~~

Ordinary tests use synthetic data and mocked transports. Docker integration and real-provider checks are separate, opt-in checks. [Validation evidence and scope, in Spanish](docs/06-resultados-ejecucion.md).

## Limitations

- Nutrition and digestibility values are estimates. The legacy OFF path uses the first match and retains approximations such as ml=g.
- Missing nutrients and LLM-parsed zeros retain legacy behavior outside the catalog path.
- Webhooks and backfill preserve manually entered calories; `POST /estimate` forces recalculation.
- Pending tasks and history do not survive a restart. Run a single instance.
- HTTP routes retain upstream access behavior and do not add authentication. Deploy on a trusted network or behind your authenticated reverse proxy.
- Local BEDCA data must be provided separately. Real-provider success is distinct from mocked tests.

## Documentation

**[Leer el README en español](docs/README.es.md)** · **[Índice de documentación en español](docs/README.md)**

| Guide | Language |
|---|---|
| [Image deployment](docker/README.md) / [Despliegue con imagen](docker/README.es.md) | English / Español |
| [Tags and history](docs/09-etiquetas-y-vista-web.md) | Español |
| [Catalogs and BEDCA](docs/11-catalogos-duckdb.md) | Español |
| [Operations and rollback](docs/07-operacion-y-retorno.md) | Español |
| [Architecture](docs/02-arquitectura.md) | Español |
| [Compatibility and API contracts](docs/03-compatibilidad-y-validacion.md) | Español |
| [Validation with real Mealie](docs/13-pruebas-mealie-real.md) | Español |

## Contributing

Bug reports, ingredient-resolution examples, documentation improvements and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). You can open issues in English or Spanish.

## Credits and license

Based on [timo-reymann/mealie-calorie-estimator](https://github.com/timo-reymann/mealie-calorie-estimator), version 1.12.3. This project retains its [GPLv3 license](LICENSE) and [third-party notices](NOTICE).

The Mealie logo belongs to the [Mealie project](https://github.com/mealie-recipes/mealie). This is an independent companion project. [Visual asset sources and attribution](docs/assets/README.md).
