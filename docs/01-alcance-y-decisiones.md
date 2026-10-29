# Alcance y decisiones

Fecha: 2026-10-29.

## Objetivo

Migrar el servicio TypeScript/Fastify a Python conservando las funcionalidades, los contratos observables y las limitaciones del original. La calidad interna puede mejorar mediante organización, tipado y pruebas, sin modificar las reglas de producto.

## Decisiones confirmadas por el usuario

| ID | Decisión | Procedencia |
|---|---|---|
| D01 | Conservar el comportamiento y las limitaciones actuales | Corrección explícita del alcance durante la conversación |
| D02 | Usar uv y FastAPI como base | Preferencia inicial y selección del documento adjunto |
| D03 | Tomar el texto adjunto como base de la migración | Última selección del usuario |
| D04 | Usar OpenAI Agents SDK para la IA | Elección explícita posterior al adjunto |
| D05 | Documentar el proceso dentro de docs | Solicitud explícita |
| D06 | Redactar y revisar el plan antes de empezar a migrar | Última solicitud del usuario |
| D07 | Usar nombres españoles para las etiquetas automáticas; conservar reglas y umbrales | Solicitud posterior explícita del usuario |

OpenAI Agents SDK sustituye a PydanticAI en el documento adjunto. Elegir el SDK no equivale a elegir un proveedor o un modelo nuevo.

D07 introduce una diferencia autorizada respecto a los nombres ingleses de la referencia. El catálogo español y la actualización de asociaciones antiguas están descritos en [etiquetas y vista web](09-etiquetas-y-vista-web.md).

## Stack de la propuesta

La selección retoma el stack del adjunto. La propuesta simplificada intermedia se conserva en el registro como alternativa considerada.

| Área | Tecnología | Uso |
|---|---|---|
| Lenguaje | Python 3.14 | Python 3.14.6 resuelto y verificado localmente y en contenedor |
| Proyecto | uv, pyproject.toml, uv.lock | Dependencias y ejecución reproducibles |
| API | FastAPI y Uvicorn | Sustitución de Fastify y servidor HTTP |
| Datos y configuración | Pydantic v2 y pydantic-settings | Modelos y variables compatibles con el original |
| Integraciones HTTP | HTTPX AsyncClient | Mealie, Open Food Facts y transporte compatible del LLM |
| IA | openai-agents, OpenAI Agents SDK | Ejecución de las dos operaciones LLM existentes |
| Caché persistente | SQLite, SQLAlchemy 2.x Core y aiosqlite | Acceso asíncrono manteniendo tablas y datos existentes |
| Esquema | Alembic | Creación y evolución controlada de las tablas de caché |
| Concurrencia | asyncio | Cola por receta, debounce, tareas y límites en memoria |
| Reintentos OFF | Tenacity | Reproducir los intentos y esperas actuales |
| Historial HTML | Jinja2 y HTML/CSS/JavaScript existentes | Mantener presentación, tema y polling |
| Utilidades | hashlib, json, logging, collections y time | Hashes, serialización, logs e historial en memoria |
| Pruebas | pytest, pytest-asyncio, respx y pytest-cov | Equivalencia y pruebas de integración simuladas |
| Calidad | Ruff y mypy | Formato, análisis y comprobación de tipos |
| Entrega | Docker y Docker Compose | Servicio Python junto a Mealie |
| CI | CircleCI adaptado a Python | Conservar la plataforma del original |

Versiones concretas resueltas en uv.lock. La implementación y sus resultados están registrados en el documento 06.

## Resoluciones técnicas del plan

Estas resoluciones del diseño se aplicaron durante la ejecución autorizada; no se atribuyen como preferencias adicionales del usuario.

- Un solo proceso Uvicorn, con tareas asíncronas para distintas recetas.
- SQLAlchemy Core evita introducir entidades ORM para una caché de cuatro tablas.
- El historial sigue en memoria; SQLite continúa dedicado a la caché.
- El SDK ejecuta una operación LLM por invocación, sin herramientas ni delegación.
- El cliente conserva LLM_ENABLED, LLM_API_KEY, LLM_BASE_URL, LLM_ENDPOINT_URL y LLM_MODEL.
- Se desactiva la exportación automática de trazas del SDK en el modo compatible. La observabilidad inicial sigue en los logs existentes.
- Las pruebas ordinarias utilizan datos sintéticos y respuestas grabadas; las comprobaciones reales se registran por separado.

### Política de límites: ajuste respecto al adjunto

El adjunto proponía aiolimiter. Su algoritmo leaky bucket no es un reemplazo equivalente de las ventanas y esperas del limitador original. La implementación reproduce la política actual con asyncio y reloj controlable en las pruebas. aiolimiter queda como alternativa evaluada, no como dependencia obligatoria.

Este ajuste se hace para cumplir D01 y debe permanecer visible durante la revisión del plan. No se cambiarán los ritmos de llamadas por adoptar una biblioteca.

## Enfoques considerados

| Enfoque | Ventaja | Decisión |
|---|---|---|
| Traducción directa con sqlite3 y cliente LLM HTTP | Menos dependencias | Considerado durante la conversación; no es la base final seleccionada |
| Monolito modular con el stack del adjunto y Agents SDK | Conserva contratos y permite comprobar cada integración | Implementado, con SDK elegido por el usuario |
| Workers distribuidos, PostgreSQL y orquestación autónoma | Permite otra escala y otros flujos | Evolución opcional fuera de esta migración |

## Dentro del alcance

- Los seis endpoints existentes y sus formatos.
- Filtros all/tagged, agrupación de eventos y procesamiento por receta.
- Hash de ingredientes, cálculo por ración y reglas de datos manuales.
- Open Food Facts, fallback LLM opcional, caché y límites de llamadas.
- Etiquetas automáticas, conservación de etiquetas del usuario y extras.
- Historial HTML/JSON, colores de Mealie y datos sintéticos de desarrollo.
- Variables de entorno y resolución de tokens por hogar.
- Docker, documentación de operación y pruebas de equivalencia.

## Fuera de la primera entrega

Redis, Taskiq, PostgreSQL, historial persistente, RAG, base vectorial, nuevos proveedores nutricionales, nuevos criterios de matching, nuevas conversiones por densidad, supervisor autónomo, subagentes, memoria conversacional y nuevas pantallas.

Tampoco se corregirán silenciosamente aproximaciones nutricionales, ceros tratados como desconocidos u otras peculiaridades observables. Una corrección funcional requerirá una decisión posterior y pruebas propias.

## Criterio de éxito

Con una misma receta, configuración y respuestas externas controladas, las dos implementaciones deben producir los mismos resultados contractuales. Solo podrán normalizarse valores variables enumerados en la matriz: identificadores de ejecución, reloj y duración. No se normalizarán diferencias nutricionales ni cambios en las escrituras.

## Referencias

- [uv](https://docs.astral.sh/uv/guides/projects/).
- [FastAPI](https://fastapi.tiangolo.com/).
- [SQLAlchemy y SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html).
- [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html).
- [aiolimiter: algoritmo](https://aiolimiter.readthedocs.io/en/stable/).
- [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk).
