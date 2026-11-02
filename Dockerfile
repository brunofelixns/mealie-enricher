FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.14.10-slim-trixie@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966 AS python-base

FROM python-base AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project --no-cache
COPY src ./src
COPY LICENSE NOTICE ./
RUN uv sync --locked --no-dev --no-editable --no-cache

FROM python-base AS runner
# x-release-please-start-version
ARG VERSION=1.0.0
# x-release-please-end
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="Mealie Enricher" \
    org.opencontainers.image.description="Self-hosted nutrition estimates and automatic tags for Mealie recipes" \
    org.opencontainers.image.source="https://github.com/brunofelixns/mealie-enricher" \
    org.opencontainers.image.url="https://github.com/brunofelixns/mealie-enricher" \
    org.opencontainers.image.licenses="GPL-3.0" \
    org.opencontainers.image.version="$VERSION" \
    org.opencontainers.image.revision="$VCS_REF"
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# uv installs the environment in builder; exclude pip and its bootstrap wheel from runtime.
RUN python -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip \
    && groupadd --gid 1000 appuser && useradd --uid 1000 --gid 1000 --create-home appuser \
    && mkdir /app/data /app/catalogs && chown appuser:appuser /app/data /app/catalogs
COPY --from=builder /app/.venv ./.venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY LICENSE NOTICE ./
USER appuser
VOLUME ["/app/data"]
EXPOSE 8000
CMD ["python", "-m", "mealie_enricher"]
