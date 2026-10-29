# Compatibilidad y validación

Estado: contratos implementados y verificados localmente; resultados finales en el documento 06.

Excepción de presentación autorizada tras la migración: las etiquetas automáticas de C26 pasan a español. Las reglas y umbrales se mantienen; las etiquetas inglesas registradas se actualizan al volver a procesar su receta. Véase [D07 y su validación](09-etiquetas-y-vista-web.md).

Fuente normativa: código en [c2dc71a1d8effe29375391f2fe50da94d27cfd7d](https://github.com/timo-reymann/mealie-calorie-estimator/tree/c2dc71a1d8effe29375391f2fe50da94d27cfd7d). Cuando README y código difieran, caracterizar el código y registrar la diferencia.

## Contratos HTTP

| ID | Método y ruta | Comportamiento que conservar |
|---|---|---|
| C01 | GET /health | status ok y timestamp ISO UTC con el formato del original |
| C02 | POST /webhook | Acepta document_data como objeto o JSON codificado; admite claves snake_case y camelCase |
| C03 | POST /webhook | 400 para document_data ausente, JSON inválido o estructura inválida, con los mensajes originales |
| C04 | POST /webhook | Evento ajeno a recipe: 200, status skipped y reason not a recipe event |
| C05 | POST /webhook | Receta válida: 202 y cuerpo con status accepted; trabajo asíncrono |
| C06 | POST /estimate | Lee el slug de body.content.slug; devuelve 202 y status accepted |
| C07 | POST /backfill | Devuelve 202 y status accepted; recorre recetas paginadas en segundo plano |
| C08 | GET /estimator/history | HTML, tema de Mealie y Cache-Control private, max-age=7200 |
| C09 | GET /estimator/history.json | Array de registros, más recientes primero |
| C10 | GET /estimator/history.json?since=... | Filtra updatedAt mayor que el timestamp en milisegundos |
| C11 | GET /estimator/history.json?since=abc | 400: since must be a timestamp in milliseconds |
| C12 | HTTP general | Mantener Content-Type, CORS y tratamiento de entradas malformadas según capturas de referencia |

Los casos malformados no descritos expresamente se capturarán con Fastify inject en la tarea 0, incluyendo content ausente, null y formatos numéricos de since. No se sustituirán por los 422 predeterminados de FastAPI.

Las rutas automáticas de documentación HTTP de FastAPI se desactivarán en esta entrega para conservar la superficie de rutas. La documentación del proyecto estará en docs.

## Reglas y peculiaridades

| ID | Área | Contrato |
|---|---|---|
| C13 | Estrategia | all/tagged con la misma comparación de nombres y slugs de etiquetas |
| C14 | Hash | SHA256 sobre la misma cadena, ordenación, cantidades, unidades, alimentos, raciones y yield |
| C15 | Número y texto | Reproducir Math.round, parseInt, parseFloat, Number y representación numérica donde afecten a contratos |
| C16 | Manual | Webhook/backfill detectan calorías no vacías solo cuando todavía no hay hash del estimador |
| C17 | Reconocimiento manual | Patch de extras con hash, lista unmatched vacía y nota; omitir nutrition |
| C18 | Estimate | Estima directamente tras el filtro; no incorpora las comprobaciones manual/hash del webhook |
| C19 | Raciones | Prioridad nullish: recipeServings, recipeYieldQuantity, 1; cero no se sustituye mediante un or de Python |
| C20 | Unidades | Mantener la tabla, prioridad standardQuantity/standardUnit y aproximación ml=g |
| C21 | Ingredientes | Sin food.name o quantity positiva, se ignoran; desconocidos conservan el comportamiento actual |
| C22 | Agregación | Mantener evaluación concurrente, nulos, sumas parciales, redondeo por ración y orden de resultados |
| C23 | OFF | Buscar un solo hit, retirar el prefijo de unidad como ahora y exigir kcal para aceptar la coincidencia |
| C24 | LLM | Prompts, parámetros y salida interpretada igual; ceros y decimales conservan las peculiaridades actuales |
| C25 | Patch | Conservar extras ajenos y campos calorie_estimator_*; omitir nutrientes desconocidos en el patch |
| C26 | Etiquetas | Mantener umbrales, orden, creación y conservación de etiquetas del usuario |
| C27 | Concurrencia | Serializar por slug, agrupar por clave de evento y permitir recetas distintas concurrentes |
| C28 | Debounce | Reiniciar la ventana en cada evento; runNow la omite; un fallo no bloquea trabajos posteriores |
| C29 | Backfill | Recorrido secuencial y uso de la misma cola por slug; no añadir deduplicación global de backfills |
| C30 | Límites | Search, product y LLM independientes; puntos por ventana de 60 s y espera de 1 s al agotarse |
| C31 | OFF: reintentos | 3 reintentos por defecto además del inicial; esperas de 500, 1000 y 2000 ms |
| C32 | Límite y reintento | La referencia consume capacidad antes de la búsqueda lógica, no antes de cada reintento OFF |
| C33 | Mealie / LLM | No añadir reintentos automáticos de lectura, escritura, validación o proveedor |
| C34 | Caché | Claves normalizadas, cuatro tablas y timestamps en milisegundos compatibles |
| C35 | Historial | En memoria, máximo 200 por defecto, TTL 24 h y pérdida al reiniciar |
| C36 | Estados | running, processed, tags-added, manual, skipped, filtered y error |
| C37 | Error | Mensaje truncado según la regla original, máximo 300; se conserva en el registro mientras exista |
| C38 | Interfaz | Polling cada 2 s, actualización incremental, enlaces configurables, tema y modo claro/oscuro |
| C39 | Tokens | Override por hogar, normalización ASCII de caracteres especiales, casing y fallback en orden original |
| C40 | SDK | Misma URL y payload LLM, una llamada por operación y ninguna llamada remota de tracing |

Detalles que requieren atención:

- El LLM de gramos interpreta una parte entera; no sustituirlo por una conversión float más permisiva.
- El parser LLM usa una regla que convierte varios valores cero a null; OFF conserva sus ceros.
- La grasa insaturada se deriva como ahora y no se limita automáticamente a cero.
- Calories:Light es menor de 350; Moderate llega a 600 y Hearty a 850, ambos inclusive.
- Digest utiliza los mismos porcentajes de energía grasa y las mismas condiciones, incluido el caso de kcal cero.
- Los nombres *Per100g se usan también en estructuras de totales y por ración: los alias externos permanecen.
- No se añade tiempo de espera de red a OFF o LLM donde el original no lo configura; Mealie conserva MEALIE_TIMEOUT_MS.
- El cliente Mealie y el de tema no construyen las subrutas de URL de la misma forma. Caracterizar MEALIE_URL con path y conservar el resultado.

## Configuración de referencia

Los defaults de esta tabla pertenecen a src/config.ts. Docker Compose tiene algunos overrides diferentes que también deben mantenerse en su propio contexto.

| Variable | Default del código |
|---|---|
| PORT | 8000 |
| MEALIE_URL | http://mealie:9000 |
| MEALIE_API_TOKEN | Vacío; se exige este o algún token por hogar |
| MEALIE_API_TOKEN_<HOUSEHOLD_ID> | Sin default |
| MEALIE_TIMEOUT_MS | 30000 |
| OFF_BASE_URL | https://world.openfoodfacts.org |
| OFF_SEARCH_BASE_URL | https://search.openfoodfacts.org |
| OFF_LANGUAGE | de |
| OFF_SEARCH_RATE_LIMIT | 10 |
| OFF_PRODUCT_RATE_LIMIT | 15 |
| OFF_CACHE_TTL | 86400 segundos |
| OFF_MAX_RETRIES | 3 |
| OFF_RETRY_BACKOFF_MS | 500 |
| OFF_USER_AGENT | Cadena original de la versión 1.12.3; caracterizar literalmente |
| LLM_ENABLED | false |
| LLM_BASE_URL | https://api.mistral.ai/v1 |
| LLM_ENDPOINT_URL | /chat/completions |
| LLM_API_KEY | Vacío |
| LLM_MODEL | mistral-small-latest |
| LLM_RATE_LIMIT | 30 |
| LLM_TEMPERATURE | 0.1 |
| LLM_MAX_TOKENS_GRAMS | 10 |
| LLM_MAX_TOKENS_NUTRIENTS | 200 |
| ESTIMATE_STRATEGY | all |
| ESTIMATE_TAG | estimate |
| EVENT_DEBOUNCE_MS | 2000 |
| CACHE_DB_PATH | data/cache.db |
| MEALIE_RECIPE_URL_TEMPLATE | MEALIE_URL seguido de /recipe/{slug} |
| DEV_SEED_HISTORY | false |
| HISTORY_MAX_ENTRIES | 200 |
| LOG_LEVEL | info |

El Compose revisado usa, entre otros overrides, OFF_LANGUAGE=en y un proveedor/modelo LLM distintos de los defaults de código. No se unificarán silenciosamente.

## Caché heredada

Tablas: nutrient_cache, unmatched_foods, llm_estimate_cache y llm_nutrient_cache.

Se conservarán las claves, los documentos JSON y las unidades de tiempo. La lectura de la caché creada por la referencia se probará antes de utilizar Alembic sobre una copia. La base original no se usará para experimentar.

El original exporta su base sql.js con retardo. La versión Python utilizará transacciones SQLite; no se exige reproducir byte por byte el archivo ni su ventana accidental de pérdida por escritura diferida. Esto es una diferencia técnica propuesta y debe ser visible al revisar el diseño.

## Método de comparación

1. Obtener una copia aislada de la referencia fijada.
2. Ejecutar sus comprobaciones; registrar los fallos existentes sin corregirlos.
3. Generar casos sintéticos con reloj controlado y servicios simulados.
4. Guardar entradas, configuración, respuestas externas, solicitudes emitidas y resultado esperado en tests/fixtures/parity.
5. Ejecutar esos mismos casos en Python.
6. Comparar estructuras JSON, hashes, nutrientes, etiquetas, número de llamadas, URL/payload y patches.

Solo se normalizan UUID de ejecución, timestamps de reloj y duraciones; su tipo, relación temporal y formato siguen siendo verificables. El HTML se compara por contenido, comportamiento y apariencia, no por espacios insignificantes entre nodos.

Tras D07, las expectativas aplican además la correspondencia autorizada de nombres/slugs de etiquetas al comparar C26 y sus flujos completos. Los fixtures originales se conservan sin editar; los casos de transición desde etiquetas inglesas se comprueban por separado.

Para concurrencia y backoff se usará reloj controlable, con comprobación de orden y tiempos de espera programados, evitando pruebas lentas basadas en dormir minutos.

## Niveles de evidencia

| Nivel | Prueba | Estado actual |
|---|---|---|
| 1 | Revisión estática del código fijado | Realizada |
| 2 | Capturas ejecutadas de la referencia | 125 casos reproducibles |
| 3 | Unitarias Python | Suite ordinaria: 187 aprobadas |
| 4 | SDK real con transporte simulado | Verificado, incluidos errores y redirecciones |
| 5 | Comparación diferencial completa | Casos y contratos C01–C40 verificados |
| 6 | Docker con Mealie de prueba y servicios simulados | 2 pruebas aprobadas, Mealie v3.19.2 |
| 7 | Proveedor LLM real configurado por el usuario | Pendiente; independiente de los anteriores |

La equivalencia bajo respuestas grabadas no garantiza respuestas idénticas entre dos ejecuciones reales de un LLM. En proveedor real se comprobarán conectividad y compatibilidad del contrato, sin prometer igualdad del contenido generado.

## Fuentes concretas

- [Rutas](https://github.com/timo-reymann/mealie-calorie-estimator/tree/c2dc71a1d8effe29375391f2fe50da94d27cfd7d/src/routes).
- [Estimación](https://github.com/timo-reymann/mealie-calorie-estimator/blob/c2dc71a1d8effe29375391f2fe50da94d27cfd7d/src/services/estimator.ts).
- [LLM](https://github.com/timo-reymann/mealie-calorie-estimator/blob/c2dc71a1d8effe29375391f2fe50da94d27cfd7d/src/services/llm-estimator.ts).
- [Configuración](https://github.com/timo-reymann/mealie-calorie-estimator/blob/c2dc71a1d8effe29375391f2fe50da94d27cfd7d/src/config.ts).
- [Caché](https://github.com/timo-reymann/mealie-calorie-estimator/blob/c2dc71a1d8effe29375391f2fe50da94d27cfd7d/src/utils/cache.ts).

## Asociación de contratos a pruebas ejecutadas

| Contratos | Archivos de pruebas (bajo tests/) |
|---|---|
| C01–C07, C12 | integration/test_http_routes.py, parity/test_end_to_end.py |
| C08–C11, C35–C38 | integration/test_history_routes.py, test_mealie_theme.py, unit/test_history.py |
| C13, C16–C19, C25 | parity/test_nutrients.py, test_end_to_end.py |
| C14–C15 | parity/test_hash.py, test_nutrients.py, test_config.py; integration/test_estimator.py |
| C20 | parity/test_conversions.py |
| C21–C22 | integration/test_estimator.py, parity/test_nutrients.py |
| C23, C31–C32 | integration/test_off_client.py |
| C24, C40 | parity/test_llm_transport.py, integration/test_agent_sdk.py, test_llm_estimator.py, test_transport_regressions.py |
| C26 | parity/test_tags.py, test_end_to_end.py |
| C27–C29 | unit/test_slug_queue.py, integration/test_processing.py, parity/test_end_to_end.py |
| C30 | unit/test_rate_limiter.py |
| C33 | integration/test_mealie_client.py, test_agent_sdk.py, test_transport_regressions.py |
| C34 | integration/test_cache.py |
| C39 | parity/test_config.py, integration/test_mealie_client.py, test_docker_smoke.py |

La suite ordinaria ejecuta las pruebas Python sin proveedores reales. Docker se verifica por separado y el capturador original requiere Node solo en desarrollo. El manifiesto identifica los fixtures; los casos temporales de cola/límites se verifican también con relojes controlados.
