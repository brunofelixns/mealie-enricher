# Catálogos DuckDB y BEDCA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Track each verification below.

**Goal:** Integrar catálogos DuckDB de solo lectura, un importador BEDCA y resolución de ambigüedades con Decisions, conservando SQLite para caché.

**Architecture:** Un lector de catálogo independiente del importador y del estimador. El estimador consulta el resolutor y conserva su fallback original solo cuando el catálogo no encuentra candidatos. Los datos originales permanecen separados de nutrientes derivados.

**Tech Stack:** Python 3.14, uv, FastAPI, DuckDB, SQLite/SQLAlchemy/Alembic, OpenAI SDK y Agents SDK, pytest.

**Spec:** [Diseño aprobado](../../11-catalogos-duckdb.md).

## Global Constraints

- No alterar contratos HTTP, etiquetas, protección de nutrición manual ni cálculos originales con el catálogo desactivado.
- Ningún dato desconocido se convierte en cero; sin densidad no convertir bases por volumen a masa.
- No incluir datos BEDCA reales ni secretos en Git o Docker.
- No consultar servicios reales desde la suite ordinaria.
- No implementar aún recopiladores de supermercados.

## Review Focus

- Cantidades en estado crudo/cocido: respetar el estado de la cantidad indicada y no inferirlo solo del plato final.
- Unidades WKG, VM, D y mg: convertir únicamente bases compatibles y conservar el registro original.
- Fallo, rechazo o elección ajena a candidatos en Decisions: devolver ambigüedad sin fallback nutricional silencioso.
- Sustitución del catálogo: un error de importación no destruye el archivo válido anterior.
- Caché y hash de receta: incorporar versión/contexto sin cambiar hashes heredados cuando el catálogo está desactivado.

## Task 1: Contratos y configuración

**Files:** `catalog/models.py`, `config.py`, `tests/unit/test_catalog_models.py`, `tests/unit/test_catalog_config.py`.

**Interfaces:** `CatalogFood`, `CatalogQuery`, `CatalogResolution`; `CatalogSettings(enabled, db_path)`; `DecisionSettings(enabled, api_key, model, timeout_seconds, min_confidence, max_concurrency)`.

- [x] Escribir pruebas de configuración explícita y modelos sin nutrientes inventados.
- [x] Ejecutarlas y observar el fallo por funcionalidad ausente.
- [x] Implementar contratos; excluir nuevas opciones del volcado de compatibilidad heredado.
- [x] Verificar las pruebas nuevas y `tests/parity/test_config.py`.

## Task 2: Catálogo e importador BEDCA

**Files:** `catalog/schema.py`, `catalog/bedca.py`, `catalog/store.py`, `catalog/cli.py`, `tests/integration/test_bedca_import.py`, `tests/integration/test_catalog_store.py`.

**Interfaces:** `import_bedca(input_dir: Path, output: Path, dataset_version: str, replace: bool = False) -> dict`; `DuckDbCatalog(path: str)` con `fingerprint`, `search(name: str, limit: int = 20) -> list[CatalogFood]`, `get(id: str) -> CatalogFood | None`, `close()`.

- [x] Pruebas con CSV sintéticos: conservación raw, kJ, mg, WKG, VM/D, NULL y entradas inválidas.
- [x] Observar fallos, implementar importación transaccional a archivo nuevo y lector de solo lectura.
- [x] Añadir CLI importación/inspección/búsqueda y tablas de futuros catálogos comerciales.
- [x] Verificar búsqueda en español, crudo/cocido, límites, no interpolación SQL y archivo anterior intacto ante error.

## Task 3: Decisions y resolutor

**Files:** `agents/catalog_decisions.py`, `catalog/resolver.py`, `tests/unit/test_catalog_resolution.py`, `tests/integration/test_catalog_decisions.py`.

**Interfaces:** `CatalogResolver(catalog, selector, cache)`; `async resolve(query: CatalogQuery) -> CatalogResolution`; `OpenAIDecisionSelector(settings)` con `async choose(query, candidates) -> tuple[str, float] | None`, `async close()`.

- [x] Pruebas de estado explícito, candidatos ambiguos, needs_context, confianza insuficiente y fallo externo.
- [x] Verificar fallo inicial y añadir selección restringida a candidatos usando Decisions oficial.
- [x] Probar claves de caché distintas para notas, instrucciones, candidatos y versiones diferentes.

## Task 4: Integración en la aplicación

**Files:** `app.py`, `services/estimator.py`, `services/processing.py`, `storage/cache.py`, `storage/schema.py`, `alembic/versions/0002_catalog_cache.py`, pruebas de integración.

- [x] Pruebas primero de BEDCA antes que OFF, ambigüedad sin fallback, origen visible y cierre de recursos.
- [x] Incorporar caché contextual con migración que conserva todas las filas heredadas.
- [x] Componer catálogo/resolutor durante lifespan y ampliar hash solo con el catálogo activo.
- [x] Verificar suite completa de compatibilidad y flujo HTTP con catálogo real local.

## Task 5: Docker, documentación y validación final

**Files:** `Dockerfile`, ambos Compose, ejemplos de entorno, `README.md`, `docs/11-catalogos-duckdb.md`, registro de progreso.

- [x] Añadir preparación de catálogo mediante perfil Docker y volumen independiente.
- [x] Documentar primera importación, activación, actualización y retorno sin descarga en arranque.
- [x] Ejecutar importación de la exportación real en carpeta ignorada y comprobar recuentos/unidades.
- [x] Ejecutar pytest, Ruff, mypy, compilación de imagen y prueba HTTP dentro de Docker.
- [x] Revisión final independiente y corregir problemas antes de informar resultados.
