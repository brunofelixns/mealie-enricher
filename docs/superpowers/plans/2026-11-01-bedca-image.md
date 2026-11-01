# Imagen con BEDCA Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Preserve the existing checkout and unrelated release work.

**Goal:** Incluir DuckDB y CSV de BEDCA en una variante Docker lista para arrancar.

**Architecture:** Capa de datos inmutable en `/opt/bedca`, generada durante build desde un contexto explícito. Mismo servicio Python y Compose, con ruta de catálogo configurable y ejemplo de entorno para la variante.

**Tech Stack:** Docker BuildKit, DuckDB, Python 3.14, pytest, Docker Compose.

**Spec:** [Diseño](../specs/2026-11-01-bedca-image-design.md).

## Global Constraints

- Mantener CSV originales y atribución; uso de datos sujeto a condiciones BEDCA.
- Mantener la imagen base y no incluir los datos externos en Git.
- No consultar OpenAI ni modificar el Mealie del usuario en las pruebas.
- No publicar imágenes ni cambiar visibilidad desde este cambio.

## Review Focus

- Un volumen de catálogo vacío no oculta el dataset incluido.
- Un dataset inválido falla durante build, antes de producir una imagen usable.
- Los CSV conservan sus bytes y no son escribibles por appuser.
- Actualizar la imagen cambia el catálogo y la firma sin sobrescribir SQLite.
- Los Compose anteriores mantienen su ruta por defecto.

## Tasks

### Task 1: Variante, configuración y pruebas reales

**Files:** `docker/Dockerfile.bedca`, `docker/bedca/NOTICE.md`, `.dockerignore`, `docker-compose.yml`, `docker/docker-compose.yml`, `docker/.env.bedca.example`, `tests/integration/test_bedca_image.py`, `tests/support/mealie_stack.py`.

**Interfaces:** Consume la CLI `python -m mealie_enricher.catalog.cli import-bedca`. Produce una imagen con `CATALOG_ENABLED=true` y `CATALOG_DB_PATH=/opt/bedca/catalogos.duckdb`.

- [x] Escribir pruebas de configuración Compose y observar el fallo por ruta forzada.
- [x] Añadir Dockerfile de variante y aviso; configurar la ruta sin cambiar el valor heredado por defecto.
- [x] Probar empaquetado, CSV, permisos y rechazo de datos inválidos con datos sintéticos.
- [x] Probar arranque y actualización de imagen con Mealie real temporal, sin importador en el despliegue.
- [x] Construir imagen local con BEDCA real y comprobar sus datos.

### Task 2: Documentación y cierre

**Files:** `docs/15-imagen-con-bedca.md`, guías Docker, documento 11, índice y registro de progreso/resultados.

- [x] Documentar construcción, despliegue, conservación de CSV, actualización y condiciones.
- [x] Ejecutar suite ordinaria, controles estáticos y regresión Docker apropiada.
- [x] Registrar límites y resultados; guardar cambios locales sin publicación.

Resultado: 358 correctas en 402,68 s (24 Docker), Ruff/formato/mypy correctos y revisión independiente sin hallazgos. La variante real linux/amd64 queda local, sin publicación de tag BEDCA. Evidencia completa en el documento 15.
