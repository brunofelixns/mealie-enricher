# syntax=docker/dockerfile:1
ARG BEDCA_DATASET_VERSION=bedca-export-2026-08-19
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.14.10-slim-trixie@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966 AS python-base

FROM python-base AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
# Bound Python compilation workers when building arm64 under QEMU.
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_CONCURRENT_INSTALLS=2
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project --no-cache
COPY src ./src
COPY LICENSE NOTICE ./
RUN uv sync --locked --no-dev --no-editable --no-cache

FROM python-base AS app-runtime
# x-release-please-start-version
ARG VERSION=1.3.0
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

# Import verified originals at build time; no network or import at application startup.
FROM app-runtime AS bedca-builder
ARG BEDCA_DATASET_VERSION
COPY --from=bedca_source --chown=1000:1000 bedca_foods.csv bedca_foodvalues.csv bedca_units.csv /tmp/bedca-bundle/source/
COPY --chown=1000:1000 docker/bedca/NOTICE.md /tmp/bedca-bundle/NOTICE.md
RUN --network=none python -m mealie_enricher.catalog.cli import-bedca \
      --input-dir /tmp/bedca-bundle/source \
      --output /tmp/bedca-bundle/catalogos.duckdb \
      --dataset-version "$BEDCA_DATASET_VERSION" > /tmp/bedca-bundle/manifest.json \
    && chmod -R a-w /tmp/bedca-bundle

# The only published image includes the application, catalog, originals and attribution.
FROM app-runtime AS runner
ARG BEDCA_DATASET_VERSION
LABEL org.opencontainers.image.description="Mealie nutrition enricher with ready-to-run BEDCA catalog and original CSVs" \
    org.opencontainers.image.licenses="GPL-3.0-only AND LicenseRef-AESAN-BEDCA" \
    dev.mealie-enricher.bedca.dataset-version="$BEDCA_DATASET_VERSION" \
    dev.mealie-enricher.bedca.terms="https://www.bedca.net/bdpub/UsoBD.pdf"
COPY --from=bedca-builder /tmp/bedca-bundle /opt/bedca
ENV CATALOG_ENABLED=true CATALOG_DB_PATH=/opt/bedca/catalogos.duckdb
USER appuser
