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

Keep BEDCA exports, local databases, real credentials and personal datasets out of commits and the base image. The separate non-commercial BEDCA variant includes verified data under its own terms. Use synthetic fixtures for ordinary tests. Preserve the upstream GPLv3 license, third-party notices and visual asset attribution.

## Automatic releases

GitHub Actions runs the full suite, including isolated Docker/Mealie/BEDCA tests, on pushes and pull requests. Successful main pushes publish both image variants and a GitHub release. Do not bump version files manually: the bot starts at 1.0.0 and applies the highest commit increment: breaking changes -> major; feat/fix -> minor; other changes -> patch. See the [workflow and recovery guide](docs/16-github-actions.md).
