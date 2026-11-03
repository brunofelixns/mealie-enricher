# Arquitectura de la migración

Estado: arquitectura implementada en Python; empaquetado y validación final en curso. Evidencia en el documento 06.

## Forma de la aplicación

Monolito modular asíncrono. Un servicio Python atiende las rutas HTTP y ejecuta
tareas en el mismo proceso. Compose configura PostgreSQL para caché e historial
mediante `DATABASE_URL`, SQLAlchemy asíncrono, psycopg 3 y Alembic.
La cola, los bloqueos y los limitadores siguen en memoria. Sin `DATABASE_URL`,
se conserva el modo anterior de caché SQLite e historial temporal.

La versión propia 1.0.0 incluye un modo opcional de catálogos con DuckDB de solo lectura y un
resolutor de identidad con reglas y Decisions. El importador se ejecuta aparte;
no escribe el catálogo durante peticiones HTTP. Véase el diseño vigente de
[catálogos](11-catalogos-duckdb.md). El diagrama siguiente documenta el flujo
heredado, que se conserva cuando `CATALOG_ENABLED=false`.

~~~mermaid
flowchart TD
    A[FastAPI: webhook, estimate y backfill] --> B[Coordinación por receta]
    B --> C[Servicio de procesamiento]
    C --> D[Conversión y búsqueda de ingredientes]
    D --> E[Open Food Facts]
    D --> F[Fallback LLM con OpenAI Agents SDK]
    D --> G[Cálculos nutricionales en Python]
    G --> H[Etiquetas y patch de Mealie]
    H --> I[Cliente Mealie]
    C --> J[Caché e historial SQL]
    K[Rutas de historial] --> J
~~~

El diagrama muestra responsabilidades, no una secuencia rígida para cada ingrediente. La conversión de unidades puede requerir LLM antes de buscar nutrientes; la consulta nutricional puede requerir otro fallback.

## Estructura implementada

~~~text
src/mealie_enricher/
  app.py
  config.py
  models.py
  compat.py
  routes/
    webhook.py
    estimate.py
    backfill.py
    history.py
  services/
    estimator.py
    unit_converter.py
    tagging.py
    processing.py
    llm_estimator.py
    mealie_theme.py
  clients/
    mealie.py
    open_food_facts.py
  agents/
    estimator_agent.py
    legacy_chat_model.py
    prompts.py
  storage/
    cache.py
    history.py
    schema.py
  runtime/
    slug_queue.py
    rate_limiter.py
    tasks.py
  templates/
    history.html
alembic/
tests/
  unit/
  integration/
  parity/
  reference/
  fixtures/
~~~

## Responsabilidades y dependencias

| Módulo | Responsabilidad | Puede utilizar |
|---|---|---|
| routes | Entrada y respuesta HTTP compatible | Servicio de procesamiento e historial |
| processing | Reglas específicas de webhook, estimate y backfill | Cola, clientes, estimador, etiquetas, historial |
| estimator | Evaluar ingredientes y agregar nutrientes | Conversor, OFF y fallback LLM |
| unit_converter / tagging | Conversiones y reglas actuales | Modelos y compatibilidad numérica |
| clients | Contratos de Mealie y OFF | HTTPX, configuración, caché y limitadores |
| agents | Ejecución LLM mediante el SDK | Transporte HTTP compatible, prompts y configuración LLM |
| storage | Caché e historial SQL; modo heredado compatible | SQLAlchemy Core, psycopg, aiosqlite y Alembic |
| runtime | Tareas, exclusión por receta y límites | asyncio, reloj y configuración |
| app | Composición y ciclo de vida | Construcción de los componentes anteriores |

Las reglas puras se prueban sin FastAPI ni conexiones. La composición es explícita; no se añade un contenedor de inyección ni una jerarquía genérica de repositorios.

## Integración de OpenAI Agents SDK

La aplicación utilizará el paquete openai-agents y el ciclo Agent/Runner. El servicio existente solo necesita dos operaciones: estimar gramos por unidad y estimar nutrientes por 100 g.

La propuesta es un agente sin herramientas, handoffs, sesiones, memoria ni acceso de escritura a Mealie. Cada invocación recibe únicamente el prompt de esa operación y termina con texto. El texto numérico o JSON se interpreta mediante las reglas actuales.

Contrato propio que debe implementar la capa SDK:

~~~python
class AgentLlmRunner:
    async def complete(self, prompt: str, *, max_tokens: int) -> str | None: ...
~~~

Reglas:

1. Mantener los prompts del original, incluido el orden y los valores interpolados.
2. Mantener el mensaje user y evitar añadir instrucciones system/developer.
3. Conservar el modelo configurado; el SDK no selecciona un modelo predeterminado nuevo.
4. Una petición al modelo por operación; sin reintentos de reparación o del transporte.
5. No añadir herramientas, response_format ni esquemas JSON al cuerpo enviado al proveedor.
6. Respetar la URL final formada por LLM_BASE_URL y LLM_ENDPOINT_URL, incluso si el path no es el estándar.
7. No habilitar trazas remotas ni requerir OPENAI_API_KEY cuando la configuración existente usa LLM_API_KEY.
8. Sin petición ni instancia de proveedor activa cuando LLM_ENABLED es false o falta LLM_API_KEY.
9. HTTP, JSON o salida inválida mantienen el resultado sin estimación y el registro correspondiente.

### Adaptador y comprobación temprana

El punto de extensión de modelos del SDK se encapsulará en legacy_chat_model.py. Ese adaptador utilizará HTTPX para conservar el contrato HTTP del original y entregará al Runner la respuesta de texto. No habrá dos implementaciones LLM alternativas en producción.

La superficie pública exacta del adaptador se comprobará contra la versión fijada del SDK al comenzar la tarea 2. La prueba debe pasar por el Runner real y un transporte simulado, no reemplazar el Runner por un mock.

Si el SDK no puede cumplir alguno de los nueve puntos, esa fase se registrará como pendiente y se resolverá la incompatibilidad antes de integrar el fallback. No se cambiará de API, modelo o endpoint silenciosamente.

La documentación oficial confirma el uso del SDK dentro de la aplicación y las extensiones por proveedor; no constituye evidencia de que este adaptador concreto ya funcione.

## Flujo de procesamiento

- Webhook valida y normaliza el evento, responde y programa la tarea con debounce.
- Estimate obtiene content.slug, responde y programa una estimación siguiendo su comportamiento específico.
- Backfill obtiene las recetas paginadas y las recorre secuencialmente utilizando la misma serialización por slug.
- Para webhook y backfill se conservan las ramas filtered, skipped, tags-added, manual y processed.
- El estimador conserva la evaluación concurrente de ingredientes de una receta.
- El servicio de etiquetado prepara el patch y el cliente Mealie realiza la escritura.
- El historial publica los estados actuales sin cambiar sus nombres ni convertir running en otro estado.

## Estado y ciclo de vida

FastAPI lifespan abre el engine SQL seleccionado, aplica Alembic, compone los
clientes y recupera el historial persistido. El servicio espera la confirmación
de persistencia al iniciar, identificar y terminar cada ejecución. Los cambios
del historial se guardan también antes de responder a consultas y al cerrar.

Se mantiene un proceso Uvicorn. Los bloqueos y límites no se comparten y los
trabajos pendientes no son durables. PostgreSQL conserva su historial: las
ejecuciones pendientes se marcan como interrumpidas al siguiente inicio, sin
repetir escrituras. La retención predeterminada es ilimitada. Véase
[PostgreSQL y operación](19-postgresql.md).

SQLAlchemy utilizará operaciones Core y transacciones cortas. Alembic reconocerá una base heredada de las cuatro tablas sin eliminar filas ni exigir un borrado previo. La revisión inicial añadirá únicamente su metadato de versión si el esquema ya coincide.

## Interfaces del diseño

Las firmas de cada tarea están en el plan. Los tipos públicos internos se declaran una sola vez en models.py, con alias para conservar camelCase en los contratos externos.

Pydantic no debe convertir automáticamente los errores actuales en respuestas 422 ni endurecer las entradas aceptadas por Fastify. Las peculiaridades JavaScript que afecten a resultados se concentran en compat.py.

## Referencias oficiales

- [SDK en la aplicación](https://developers.openai.com/api/docs/guides/agents/sdk).
- [Modelos, proveedores y transporte](https://developers.openai.com/api/docs/guides/agents/models).
- [Ejecución y estado](https://developers.openai.com/api/docs/guides/agents/running-agents).
- [Trazas del SDK](https://developers.openai.com/api/docs/guides/agents/integrations-observability).

Consulta: 2026-10-29. La integración real con el proveedor sigue pendiente.
