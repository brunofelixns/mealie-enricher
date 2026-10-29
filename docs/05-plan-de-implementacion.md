# Migración equivalente a Python: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkboxes for tracking.

**Goal:** Reproducir el servicio 1.12.3 en Python con los mismos contratos y limitaciones, utilizando OpenAI Agents SDK en el fallback LLM.

**Architecture:** Monolito modular asíncrono con un proceso Uvicorn. Rutas, reglas de estimación, integraciones y estado tienen responsabilidades separadas. Los cálculos y las escrituras siguen controlados por el servicio.

**Tech Stack:** Python 3.14.6, uv, FastAPI, Uvicorn, Pydantic v2, pydantic-settings, HTTPX, OpenAI Agents SDK, SQLite, SQLAlchemy Core, aiosqlite, Alembic, Tenacity, asyncio, Jinja2, pytest, pytest-asyncio, respx, pytest-cov, Ruff, mypy, Docker Compose y CircleCI.

**Spec:** [Alcance](01-alcance-y-decisiones.md), [arquitectura](02-arquitectura.md) y [compatibilidad](03-compatibilidad-y-validacion.md).

**Estado:** Ejecución autorizada por el usuario el 2026-10-29. Fases 0 a 8 completadas con verificación local. Revisión final y correcciones realizadas; proveedor LLM real y CI remoto sin ejecutar. Los resultados observados se registran en el documento 06; la operación con proveedor real se documenta por separado.

## Global Constraints

- Referencia fija: c2dc71a1d8effe29375391f2fe50da94d27cfd7d, versión declarada 1.12.3.
- Conservar el comportamiento y las limitaciones actuales.
- Usar OpenAI Agents SDK para la IA.
- Un solo proceso Uvicorn, con tareas asíncronas para distintas recetas.
- El historial sigue en memoria; SQLite continúa dedicado a la caché.
- El SDK ejecuta una operación LLM por invocación, sin herramientas ni delegación.
- El cliente conserva LLM_ENABLED, LLM_API_KEY, LLM_BASE_URL, LLM_ENDPOINT_URL y LLM_MODEL.
- No añadir reintentos LLM, mensajes system/developer, response_format, trazas remotas ni selección implícita de modelo.
- Mantener SQLAlchemy/Alembic del adjunto; reproducir el limitador con asyncio según el ajuste documentado.
- Conservar los defaults del código y los overrides de Compose como contextos distintos.
- La implementación no requiere llamadas a proveedores reales para sus pruebas ordinarias.
- No utilizar una instancia o base de datos de producción para verificar el plan.
- Mantener LICENSE y NOTICE del material reutilizado.
- Actualizar docs/04-registro-de-progreso.md después de cada tarea verificada.

## Review Focus

1. Datos manuales: diferenciar webhook/backfill de estimate y conservar el efecto del hash tras el reconocimiento.
2. Entradas de frontera: null, cero, cadenas numéricas, Unicode, redondeos de mitad y errores HTTP actuales.
3. Fallos de red: OFF con 429/5xx, reintentos agotados, URL LLM personalizada y ninguna repetición automática de un patch.
4. Concurrencia: ráfagas del mismo slug, claves distintas, backfill simultáneo y recuperación de la cola tras un fallo.
5. Estado heredado: caché sql.js existente, tokens por hogar, historial que expira y diferencias entre código/Compose.

Estas cinco clases se cubren respectivamente en las tareas 6; 1 y 3; 2 y 5; 4 y 6; 1, 4 y 7.

## Orden y entregables

| Tarea | Entregable | Depende de |
|---|---|---|
| 0 | Referencia ejecutada y casos de comparación capturados | Revisión del plan |
| 1 | Proyecto, modelos y configuración compatibles | 0 |
| 2 | SDK integrado y probado con transporte simulado | 1 |
| 3 | Reglas puras y compatibilidad JavaScript | 1 |
| 4 | Caché, cola, limitadores e historial | 1 |
| 5 | Clientes Mealie/OFF y servicio de fallback LLM | 2 y 4 |
| 6 | Estimación completa, procesamiento y rutas de escritura | 3, 4 y 5 |
| 7 | Historial web, tema y datos de desarrollo | 4 y 6 |
| 8 | Docker, CI, comparación completa y entrega | Todas |

El orden de ejecución propuesto es secuencial, de 0 a 8. La fase 2 se adelanta para resolver pronto la compatibilidad del SDK. No se comenzará una fase dependiente si falta su contrato.

## Archivos y contratos comunes

La estructura de producción está detallada en el documento 02. La documentación ya existente se mantiene y actualiza; no se vuelve a generar desde cero.

models.py declarará los tipos de la referencia: MealieIngredient, MealieUnit, MealieFood, MealieNutrition, MealieTag, MealieRecipe, MealieRecipePatch, NutrientSet, IngredientMatch, EstimateResult, NutritionPatch y OffLookupResult. Añadirá IngredientOutcome, ExecutionRecord y ExecutionHandle para los contratos internos. Las propiedades externas conservarán sus alias originales.

Los servicios emplearán composición explícita. Las firmas mostradas son decisiones de diseño para la futura implementación; los métodos de extensión del SDK se tomarán de la versión fijada, sin inventar una API externa.

---

## Tarea 0: fijar y caracterizar la referencia

**Archivos:**
- Crear .gitignore, tests/reference/README.md y tests/reference/capture.mts.
- Crear tests/fixtures/parity/manifest.json y archivos JSON de casos.
- Usar .reference/mealie-calorie-estimator como copia de trabajo descartable y excluida del control de versiones.
- Actualizar el registro y la matriz con cualquier diferencia observada.

**Interfaces:**
- Produce manifest.json con upstream_commit, normalization y cases.
- Cada caso declara id, area, input, environment, external_responses, expected_requests y expected_result.
- area identifica config, hash, conversion, tags, estimator, cache, queue, limiter, http o history.
- Los fixtures son sintéticos y no incluyen secretos, identificadores de usuarios reales ni datos de recetas privadas.

- [x] Obtener el repositorio original en .reference y hacer checkout de la referencia fija, sin editar sus fuentes.
- [x] Ejecutar npm ci, npm run typecheck y npm test en esa copia. Registrar versiones y resultados, incluidos fallos preexistentes.
- [x] Implementar el capturador con las funciones y rutas reales del original, transporte simulado y reloj controlado. Node solo se necesita para esta referencia de desarrollo.
- [x] Capturar todas las clases C01-C40 de la matriz, incluyendo cuerpos malformados, Number de since vacío, redondeos, tokens y estados.
- [x] Validar que el manifiesto identifica el commit correcto y que cada caso tiene resultado y solicitudes esperadas. Ejecutar la captura dos veces y comparar tras las normalizaciones permitidas.

**Comprobación de la referencia:**

~~~powershell
git -C .reference/mealie-calorie-estimator rev-parse HEAD
Push-Location .reference/mealie-calorie-estimator
try {
    npm ci
    npm run typecheck
    npm test
    npm exec -- tsx ../../tests/reference/capture.mts
} finally {
    Pop-Location
}
~~~

**Salida:** HEAD coincide con el commit fijado y los fixtures son reproducibles. Un fallo de la suite upstream se documenta; no se convierte en una reparación funcional ni se oculta. Los casos afectados deben disponer de una captura reproducible antes de migrarlos.

## Tarea 1: crear el proyecto, modelos y configuración

**Archivos:**
- Crear pyproject.toml, uv.lock, .python-version, .env.example.
- Crear src/mealie_enricher/__init__.py, config.py, models.py y compat.py.
- Crear tests/conftest.py, tests/parity/cases.py, tests/parity/test_config.py y tests/unit/test_models.py.

**Interfaces:**
- load_settings(env: Mapping[str, str] | None = None) -> Settings.
- get_mealie_token(settings: Settings, household_id: str | None = None) -> str.
- Settings agrupa MealieSettings, OffSettings, LlmSettings, EstimateSettings, EventSettings, CacheSettings e HistorySettings.
- load_case(case_id: str) -> dict, en tests/parity/cases.py, carga un fixture del manifiesto.
- Produce los modelos comunes y sus alias, incluidos tipos nulos y campos opcionales.

- [x] Escribir pruebas de configuración contra fixtures antes de implementar su carga. Incluir ausencia total de token, default por hogar, casing, signos, default vacío y primer override.
- [x] Comprobar que fallan por ausencia de la implementación.
- [x] Crear el paquete y resolver Python/dependencias con uv. Verificar Python 3.14 y fijarlo si la resolución funciona; registrar cualquier incompatibilidad antes de proponer otra versión.
- [x] Implementar modelos y configuración sin hacer más estrictos los contratos capturados. No exigir clave LLM para arrancar con el fallback deshabilitado o incompleto.
- [x] Configurar Ruff, mypy y pytest. Fijar versiones en uv.lock y conservar los defaults exactos del documento 03.

**Aserciones de ejemplo:**

~~~python
settings = load_settings({"MEALIE_API_TOKEN": "test-token"})
assert settings.port == 8000
assert settings.off.language == "de"
assert settings.llm.enabled is False
assert settings.llm.max_tokens_grams == 10
assert settings.llm.max_tokens_nutrients == 200
~~~

**Verificación:** uv run pytest tests/parity/test_config.py tests/unit/test_models.py -q; uv run ruff check src tests alembic; uv run mypy src.

**Salida:** pruebas pasan y lockfile reproducible. Los comandos no contactan con proveedores.

## Tarea 2: comprobar OpenAI Agents SDK y el transporte compatible

**Archivos:**
- Crear agents/estimator_agent.py, agents/legacy_chat_model.py y agents/prompts.py.
- Crear tests/integration/test_agent_sdk.py y tests/parity/test_llm_transport.py.
- Las rutas de producción de esta y las siguientes tareas son relativas a src/mealie_enricher.

**Interfaces:**
- AgentLlmRunner(settings: LlmSettings, http: httpx.AsyncClient).
- AgentLlmRunner.complete(prompt: str, *, max_tokens: int) -> Awaitable[str | None].
- build_grams_prompt(unit_name: str, food_name: str) -> str.
- build_nutrients_prompt(food_name: str) -> str.
- El adaptador de modelo encapsula las interfaces públicas de la versión instalada de openai-agents.

- [x] Escribir pruebas que ejecuten Runner real y capturen la solicitud con respx. Afirmar URL, un único mensaje user, model, temperature, max_tokens y una única petición.
- [x] Añadir casos para endpoint personalizado, proveedor compatible sin credencial OpenAI, ausencia de clave, LLM deshabilitado, 429/500, JSON inválido, choices vacío y respuesta sin content.
- [x] Comprobar los fallos iniciales. Inspeccionar la versión fijada y sus interfaces públicas antes de implementar el adaptador.
- [x] Implementar un Agent y el puente de modelos descrito en el diseño. Usar HTTPX para reproducir el cuerpo y URL de referencia. Desactivar trazas remotas, herramientas, memoria, streaming y repeticiones.
- [x] Añadir una aserción de cero peticiones al host de trazas y de cero llamadas cuando el LLM está deshabilitado. Los errores conservan el resultado None.

**Aserciones del contrato de transporte:**

~~~python
assert captured_json == case["expected_requests"][0]["json"]
assert captured_url == case["expected_requests"][0]["url"]
assert provider_call_count == 1
assert tracing_call_count == 0
~~~

Las variables de estas aserciones las obtiene el fixture de transporte del test, no un proveedor real.

**Verificación:** uv run pytest tests/integration/test_agent_sdk.py tests/parity/test_llm_transport.py -q; uv run mypy src.

**Salida:** las pruebas atraviesan el SDK instalado y conservan el contrato HTTP. Esto no acredita conectividad con un proveedor real. Si no se cumple el contrato, resolver el adaptador antes de integrar el fallback.

## Tarea 3: migrar reglas puras y semántica numérica

**Archivos:**
- Completar compat.py.
- Crear services/unit_converter.py, services/estimator.py y services/tagging.py.
- Crear tests/parity/test_hash.py, test_conversions.py, test_nutrients.py y test_tags.py.

**Interfaces:**
- compute_ingredient_hash(recipe: MealieRecipe) -> str.
- convert_to_grams(quantity: float, unit: MealieUnit | None) -> float | None.
- should_estimate(recipe: MealieRecipe, settings: EstimateSettings) -> bool.
- has_manual_calories(recipe: MealieRecipe) -> bool.
- build_manual_ack_patch(recipe: MealieRecipe, ingredient_hash: str) -> NutritionPatch.
- aggregate_ingredients(recipe: MealieRecipe, outcomes: list[IngredientOutcome | None]) -> EstimateResult.
- build_nutrition_patch(result: EstimateResult, ingredient_hash: str) -> NutritionPatch.
- compute_tags(nutrients: NutrientSet) -> list[str].
- per_serving_from_recipe_nutrition(nutrition: MealieNutrition | None) -> NutrientSet.
- merge_tags(recipe: MealieRecipe, auto_tags: list[MealieTag], old_slugs: list[str]) -> list[MealieTag].
- tags_are_complete(recipe: MealieRecipe) -> bool.

- [x] Escribir pruebas parametrizadas sobre los fixtures de hash, conversión, nutrientes y etiquetas.
- [x] Añadir fronteras explícitas: unidades ml/cup/piece, raciones null/cero, mitad .5, representación de cantidades, Unicode y nutrientes nulos/cero.
- [x] Ejecutar para observar el fallo inicial.
- [x] Implementar las reglas sin I/O. Encapsular las conversiones JavaScript que afecten al resultado en compat.py y utilizarlas también desde los parsers posteriores.
- [x] Verificar omisión de nutrition en reconocimiento manual, conservación de extras y límites de etiquetas.

**Aserciones mínimas:**

~~~python
assert convert_to_grams(2, gram_unit) == 2
assert convert_to_grams(200, milliliter_unit) == 200
assert convert_to_grams(2, piece_unit) is None
assert compute_tags(nutrients_350)[0] == "Calories:Moderate"
assert compute_tags(nutrients_600)[0] == "Calories:Moderate"
assert compute_tags(nutrients_850)[0] == "Calories:Hearty"
~~~

**Verificación:** uv run pytest tests/parity/test_hash.py tests/parity/test_conversions.py tests/parity/test_nutrients.py tests/parity/test_tags.py -q.

**Salida:** comparación exacta de resultados frente a la referencia, sin tolerancias nutricionales añadidas.

## Tarea 4: implementar estado, caché y coordinación

**Archivos:**
- Crear storage/cache.py, storage/schema.py y storage/history.py.
- Crear runtime/slug_queue.py, runtime/rate_limiter.py y runtime/tasks.py.
- Crear alembic.ini, alembic/env.py, alembic/script.py.mako y alembic/versions/0001_legacy_cache.py.
- Crear tests/integration/test_cache.py, tests/unit/test_slug_queue.py, test_rate_limiter.py y test_history.py.

**Interfaces:**
- SqliteCache.open(path: str, ttl_ms: int) -> Awaitable[SqliteCache]; close() -> Awaitable[None].
- Métodos asíncronos de SqliteCache: get_nutrients(food_name) -> NutrientSet | None; set_nutrients(food_name, nutrients) -> None; get_grams(unit_name, food_name) -> float | None; set_grams(unit_name, food_name, grams) -> None; get_llm_nutrients(food_name) -> NutrientSet | None; set_llm_nutrients(food_name, nutrients) -> None.
- Los nombres de alimentos/unidades son str; nutrients es NutrientSet y grams es float.
- SlugQueue.run(slug: str, key: str, task: Callable[[], Awaitable[None]]) -> Awaitable[None].
- SlugQueue.run_now(slug: str, task: Callable[[], Awaitable[None]]) -> Awaitable[None].
- RateLimiter.wait(kind: Literal["search", "product", "llm"]) -> Awaitable[None].
- ExecutionHistory.record_start(trigger: str, slug: str) -> ExecutionHandle; get_history(since: float | None = None) -> list[ExecutionRecord].
- ExecutionHandle.set_recipe(name: str, household_id: str | None) -> None; complete(status: str, changes: list[str], estimate: ExecutionEstimate | None = None) -> None; fail(error: Exception | str) -> None.
- ExecutionEstimate se declara en models.py con nutrients, matchedCount y unmatchedCount, como en la referencia.
- TaskRegistry.start(task: Awaitable[None]) -> None; close() -> Awaitable[None]. Mantiene referencias fuertes y recupera excepciones.
- Reloj/sleep se inyectan como callables en los componentes temporales para probarlos.

- [x] Escribir pruebas de lectura de una base heredada, normalización de claves, TTL, hit/miss y conservación de filas al aplicar Alembic.
- [x] Escribir pruebas de orden, coalescencia por clave, reinicio de debounce, slugs concurrentes, run_now y fallo de una tarea seguido de otra correcta.
- [x] Añadir pruebas de ventanas de 60 s, espera de 1 s y limitadores independientes; probar historial con 200 entradas, TTL de 24 h y error truncado a 300.
- [x] Ejecutar los fallos iniciales e implementar componentes. Mantener las cuatro tablas originales, aunque unmatched_foods no se utilice en el flujo principal.
- [x] Aplicar la revisión Alembic a una base vacía y a una copia heredada. Esquema ya existente compatible: conservar filas y añadir el metadato de revisión.

**Aserciones de regresión:**

~~~python
assert observed_order == ["first-start", "first-end", "second-start", "second-end"]
assert coalesced_run_count == 1
assert history.get_history(since=last_updated_at) == []
assert existing_rows_after_upgrade == existing_rows_before_upgrade
~~~

**Verificación:** uv run pytest tests/integration/test_cache.py tests/unit/test_slug_queue.py tests/unit/test_rate_limiter.py tests/unit/test_history.py -q.

**Salida:** persistencia compatible y estado temporal reproducible. Las pruebas usan directorios temporales, nunca una caché del usuario.

## Tarea 5: migrar clientes externos y fallback

**Archivos:**
- Crear clients/mealie.py, clients/open_food_facts.py y services/llm_estimator.py.
- Crear tests/integration/test_mealie_client.py, test_off_client.py y test_llm_estimator.py.

**Interfaces:**
- MealieClient(settings: Settings, http: httpx.AsyncClient).
- get_recipe(slug: str, household_id: str | None = None) -> Awaitable[MealieRecipe].
- patch_recipe(slug: str, patch: MealieRecipePatch, household_id: str | None = None) -> Awaitable[None].
- get_all_recipes(household_id: str | None = None) -> Awaitable[list[str]].
- get_or_create_tags(names: list[str], household_id: str | None = None) -> Awaitable[list[MealieTag]].
- OffClient(settings: OffSettings, http: httpx.AsyncClient, cache: SqliteCache, limiter: RateLimiter).
- OffClient.lookup_nutrients(food_name: str, unit_name: str | None = None) -> Awaitable[OffLookupResult].
- LlmEstimator(settings: LlmSettings, runner: AgentLlmRunner, cache: SqliteCache, limiter: RateLimiter).
- LlmEstimator.estimate_grams(quantity: float, unit_name: str, food_name: str) -> Awaitable[float | None].
- LlmEstimator.estimate_nutrients(food_name: str) -> Awaitable[NutrientSet | None].

- [x] Escribir pruebas con respx para paginación, 204, JSON inválido, error Mealie, timeout, token por hogar y URL con subruta.
- [x] Para OFF, comprobar primer hit, kcal ausente, ceros válidos, ausencia de hit, 429/503 y cuatro intentos totales con backoff de 500/1000/2000 ms.
- [x] Para el fallback, probar caché de gramos por unidad, multiplicación por cantidad, parte entera, JSON con fences, ceros convertidos a null y errores sin reparación adicional.
- [x] Observar los fallos e implementar. Configurar Tenacity para reproducir la política actual y no multiplicarla con la del cliente HTTP.
- [x] Verificar que un error de patch no dispara una segunda escritura y que un fallo LLM realiza una única llamada.

**Aserciones de red:**

~~~python
assert off_request_count == 4
assert recorded_backoffs_ms == [500, 1000, 2000]
assert patch_request_count == 1
assert llm_request_count == 1
~~~

Las cuatro aserciones pertenecen a escenarios separados: OFF agotado, patch fallido y LLM fallido.

**Verificación:** uv run pytest tests/integration/test_mealie_client.py tests/integration/test_off_client.py tests/integration/test_llm_estimator.py -q.

**Salida:** contratos HTTP y fallback compatibles, con proveedores simulados.

## Tarea 6: integrar estimación, procesamiento y API

**Archivos:**
- Completar services/estimator.py y services/tagging.py.
- Crear services/processing.py, routes/webhook.py, routes/estimate.py, routes/backfill.py y app.py.
- Crear tests/integration/test_estimator.py, test_processing.py, test_http_routes.py y tests/parity/test_end_to_end.py.

**Interfaces:**
- Estimator(off: OffClient, llm: LlmEstimator); estimate_recipe(recipe: MealieRecipe) -> Awaitable[EstimateResult].
- TaggingService(mealie: MealieClient, estimator: Estimator).
- TaggingService.resolve_and_merge_tags(recipe: MealieRecipe, nutrients: NutrientSet, household_id: str | None) -> Awaitable[tuple[list[MealieTag], list[str]]].
- TaggingService.estimate_and_tag(recipe: MealieRecipe, ingredient_hash: str, household_id: str | None) -> Awaitable[EstimateAndTagResult].
- EstimateAndTagResult se declara en models.py con calories, tagSlugs, perServingNutrients, matchedCount y unmatchedCount.
- ProcessingService(settings: Settings, mealie: MealieClient, tagging: TaggingService, queue: SlugQueue, history: ExecutionHistory).
- ProcessingService.process_webhook(slug: str), process_estimate(slug: str) y process_backfill() -> Awaitable[None].
- create_app(settings: Settings | None = None) -> FastAPI.

- [x] Escribir pruebas de conversión/OFF/fallback concurrentes y de sus errores, conservando orden de resultados y nutrientes desconocidos.
- [x] Escribir pruebas de cada rama de webhook y backfill. La misma receta manual debe conservar nutrition en webhook/backfill y seguir la estimación en estimate.
- [x] Escribir pruebas HTTP mediante HTTPX ASGITransport para C01-C12, incluyendo los cuerpos y códigos capturados. Probar ráfagas y backfill concurrente con un webhook.
- [x] Ejecutar los fallos e implementar composición y lifespan. Inicializar recursos al arrancar; desactivar rutas automáticas de docs y conservar CORS.
- [x] Integrar SDK, caché, límites y cola reales con transporte simulado. Verificar que un patch conserva extras ajenos y etiquetas del usuario.

**Aserciones contractuales:**

~~~python
assert response.status_code == 202
assert response.json() == {"status": "accepted"}
assert "nutrition" not in manual_webhook_patch
assert estimate_patch == case["expected_result"]["patch"]
~~~

Las pruebas asíncronas deben esperar la finalización mediante los handles de prueba; no mediante sleeps arbitrarios.

**Verificación:** uv run pytest tests/integration/test_estimator.py tests/integration/test_processing.py tests/integration/test_http_routes.py tests/parity/test_end_to_end.py -q.

**Salida:** flujos funcionales comparados, todavía sin conexión a Mealie real.

## Tarea 7: conservar historial, tema y experiencia web

**Archivos:**
- Crear routes/history.py, services/mealie_theme.py y templates/history.html.
- Crear storage/dev_seed.py para los datos sintéticos de desarrollo.
- Crear tests/integration/test_history_routes.py y test_mealie_theme.py.
- Actualizar app.py y el registro de progreso.

**Interfaces:**
- MealieThemeClient(settings: MealieSettings, http: httpx.AsyncClient).
- MealieThemeClient.get_theme() -> Awaitable[MealieTheme].
- MealieTheme se declara en models.py con paletas light y dark y las claves de color de la referencia.
- seed_dev_history(settings: HistorySettings, history: ExecutionHistory) -> None.
- Las rutas consumen ExecutionHistory y MealieThemeClient, sin acceder directamente al engine.

- [x] Escribir pruebas de snapshot JSON, since válido/vacío/inválido, orden, cache headers y Content-Type.
- [x] Probar caché de tema de 2 h, fallback de 30 s, colores inválidos y seeding solo cuando está habilitado.
- [x] Observar fallos e implementar el HTML existente como plantilla Jinja2, manteniendo mensajes, columnas, colores, enlaces y JavaScript de polling.
- [x] Comprobar en navegador, con datos sintéticos, processed, tags-added, manual, skipped, filtered, error y running en claro/oscuro.
- [x] Recargar y reiniciar para confirmar las limitaciones de memoria documentadas. Registrar evidencia visual sin añadir un nuevo framework frontend.

**Aserciones mínimas:**

~~~python
assert response.headers["cache-control"] == "private, max-age=7200"
assert invalid_since_response.status_code == 400
assert history_after_restart == []
~~~

**Verificación:** uv run pytest tests/integration/test_history_routes.py tests/integration/test_mealie_theme.py -q; revisión visual local registrada.

**Salida:** historial y tema conservados; resultados de prueba y revisión visual documentados por separado.

## Tarea 8: empaquetar, comparar y preparar la entrega

**Archivos:**
- Crear Dockerfile, docker-compose.yml, .dockerignore y README.md.
- Crear tests/support/mock_off_server.py y tests/integration/test_docker_smoke.py.
- Adaptar .circleci/config.yml y conservar LICENSE y NOTICE del código reutilizado.
- Actualizar todos los documentos con resultados reales.

**Interfaces:**
- Arranque documentado: uv run uvicorn mealie_enricher.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 1, para el ejemplo local.
- El entrypoint de contenedor respetará PORT, cuyo default es 8000; no lo fijará incondicionalmente a 8000.
- Compose conservará sus variables/overrides y el perfil de prueba con Mealie v3.19.2 de la referencia.
- Runtime Python sin Node; Node queda limitado a la captura de referencia.

- [x] Escribir el smoke test para health, webhook/estimate y lectura de historial con transporte de prueba, antes de cerrar el empaquetado.
- [x] Crear imagen sin dependencias de desarrollo, usuario sin privilegios y volumen de caché. Aplicar Alembic de forma compatible al iniciar.
- [x] Configurar CI: uv sync --locked, Ruff, mypy, pytest y construcción. No añadir un umbral de cobertura arbitrario; conservar el informe.
- [x] Ejecutar toda la comparación diferencial. Resolver diferencias de migración; registrar cualquier peculiaridad heredada sin cambiar la referencia.
- [x] Ejecutar Docker en entorno aislado de pruebas, con Mealie de prueba y mock OFF. No modificar una instancia existente.
- [x] Preparar copia de seguridad de la caché y procedimiento de retorno al contenedor original. No sobrescribir la base original.
- [x] Documentar la verificación LLM real como pendiente hasta disponer de la configuración elegida. Si se realiza después, usar una comprobación acotada y registrar proveedor/modelo sin revelar claves.

**Comandos de cierre local:**

~~~powershell
uv sync --locked
uv run ruff check src tests alembic
uv run ruff format --check src tests alembic
uv run mypy src
uv run pytest --cov=mealie_enricher --cov-report=term-missing
docker compose config --quiet
docker compose build
uv run pytest tests/integration/test_docker_smoke.py -q
~~~

El smoke test gestiona un Compose project y volúmenes de prueba propios, inicia los servicios requeridos, espera readiness y comprueba el resultado antes de limpiarlos. La existencia de un test no acredita que Docker se haya ejecutado.

**Salida:** pruebas completas, diferencias justificadas y manual de ejecución. Las comprobaciones que no hayan podido ejecutarse se enumeran expresamente.

## Criterios de entrega

- [x] C01-C40 están asociados a pruebas ejecutadas y sus resultados.
- [x] Los fixtures conservan la referencia fija y el proceso de regeneración.
- [x] URL/payload LLM atraviesan Agents SDK y coinciden con las capturas.
- [x] Ningún flujo añade llamadas, reintentos o escrituras no previstos.
- [x] La caché heredada se lee y actualiza sobre una copia sin pérdida de filas.
- [x] La interfaz conserva apariencia, tema y actualización del historial.
- [x] uv.lock, imagen y documentación permiten reproducir la ejecución.
- [x] Los resultados de unitarias, equivalencia, Docker y proveedor real están diferenciados.
- [x] Se ha revisado el conjunto completo contra alcance y arquitectura.

## Control de avance y revisiones

Cada tarea termina registrando archivos, comandos, resultados y pendientes. Cuando exista un repositorio Git y se haya acordado conservar cambios en él, los commits se mantendrán enfocados por tarea; este plan no inicializa Git ni ordena publicar nada.

Una incompatibilidad técnica se resuelve en su módulo y se vuelve a comprobar. Un cambio de comportamiento, proveedor por defecto o alcance se documenta como decisión nueva antes de ejecutarlo.

La ejecución fue autorizada el 2026-10-29. Continuar por la primera tarea pendiente y registrar evidencia antes de marcarla completada.
