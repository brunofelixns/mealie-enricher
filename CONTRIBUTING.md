# Contributing to Mealie Enricher

[Project overview](README.md) · [Documentación en español](docs/README.md)

Issues and pull requests in English or Spanish are welcome. For a bug report, include the application/image version, your Mealie version, relevant configuration names and a minimal ingredient example. Remove API tokens, personal recipe information and private URLs from logs before sharing them.

For a substantial behavior change, open an issue first so we can discuss compatibility with Mealie and the upstream estimator. Small documentation fixes can go straight to a pull request.

## Local setup and checks

Use Python 3.14 and uv:

~~~sh
uv sync --locked
uv run ruff check src tests alembic
uv run ruff format --check src tests alembic
uv run mypy src
uv run pytest
~~~

The ordinary suite uses synthetic data and mocked network responses. Do not point tests at your production Mealie instance. Docker integration tests are opt-in; consult [the validation guide](docs/12-validacion-catalogos.md) and [isolated Mealie scenarios](docs/13-pruebas-mealie-real.md).

Keep changes focused, preserve public HTTP contracts and personal Mealie tags, and describe the behavior changed and the verification performed in your pull request. Runtime changes should include relevant regression coverage. Use conventional commit messages such as `fix: preserve personal recipe tags` or `docs: clarify Docker setup`.

## Data and attribution

Keep BEDCA exports, local databases, real credentials and personal datasets out of commits and images. Use synthetic fixtures for examples and tests. Preserve the upstream GPLv3 license, third-party notices and visual asset attribution.
