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

## Evolución aprobada el 2026-10-31: catálogos

La primera entrega compatible queda como referencia histórica. El usuario
autoriza ahora una ampliación opcional, detallada en
[11-catalogos-duckdb.md](11-catalogos-duckdb.md):

- D08: SQLite permanece exclusivamente como caché; DuckDB guarda catálogos
  persistentes, consultados en solo lectura por el servicio.
- D09: importación explícita y versionada de BEDCA con originales, procedencia,
  validación y nutrientes derivados separados. No redistribuir el dataset.
- D10: OpenAI Decisions elige entre candidatos o se abstiene; Agents SDK conserva
  su integración existente y Python mantiene los cálculos y etiquetas.
- D11: preparar tablas de productos, nutrientes propios, presentaciones,
  supermercados y precios fechados; recopiladores reales quedan para otra fase.
- D12: con catálogo activo, contexto/versión invalidan hash y caché; se respetan
  estados y notas, no se supone ml=g y se limpian valores automáticos obsoletos.
  Con catálogo desactivado se mantienen los contratos de la migración original.

## Evolución del 2026-11-01: variante con datos incluidos

- D13: el usuario solicita incluir DuckDB y conservar los CSV en Docker; confirma
  distribución pública no comercial. Esta decisión sustituye la exclusión de
  datos de la imagen en D09 únicamente para la variante BEDCA. Los datos siguen
  excluidos de Git y de la imagen base.
- El mantenedor valida y genera el catálogo durante build. El arranque consulta
  `/opt/bedca/catalogos.duckdb` sin descargas, importaciones ni escrituras de datos.
- Se conservan los CSV originales, manifiesto y condiciones propias de BEDCA.
  La licencia del código no concede derechos adicionales sobre el dataset.
- [Diseño y operación](15-imagen-con-bedca.md). Este cambio prepara y prueba
  la imagen local; no publica un paquete ni modifica su visibilidad.

## D14: versión propia del proyecto

El usuario establece **1.0** como versión correcta de Mealie Enricher. Se utiliza
**1.0.0** en los metadatos Python y Docker. La versión del proyecto tiene
numeración propia; no continúa la del repositorio original. Los números antiguos
se conservan únicamente en evidencias históricas y referencias al upstream.
Cambiar el código local no renombra ni publica imágenes de GHCR.

## D15: publicación automática desde main

El usuario solicita GitHub Actions para ejecutar toda la suite al subir código
y publicar en GHCR solo si pasa, con versión automática. Se mantiene 1.0.0 como
primera versión propia. El [documento 16](16-github-actions.md) registra la política
de commits, las variantes, los permisos y la recuperación de fallos.

## D16: main protegida y publicación mediante Release Please

El usuario solicita aplicar PR obligatorias y una PR automática de publicación.
Sustituye D15 en cuanto al disparador de publicación: una PR funcional fusionada
no publica; fusionar la PR de versión crea tag/release y solicita la publicación
de GHCR tras validar ese commit. El bot no puede escribir directamente en main
ni fusiona su PR. Se conservan la política de versiones, las pruebas y BEDCA.
Se utiliza GITHUB_TOKEN, sin credenciales nuevas. Su PR requiere aprobar el CI
de pull_request; workflow_dispatch se reserva para publicar releases. La opción
de GitHub App para quitar esa aprobación adicional se consulta al usuario.
La [guía vigente](16-github-actions.md) distingue el flujo de su evidencia histórica.

## D17: GitHub App para el CI automático de Release Please

El usuario elige una App dedicada para que los eventos de las PR del bot
arranquen CI sin la aprobación que exige GITHUB_TOKEN. Solo se instala en
mealie-enricher, con Contents/Pull requests/Issues write y Metadata read.
El workflow genera tokens temporales limitados y los revoca al terminar.
La clave queda únicamente como secreto de Actions; Client ID y slug son variables.
La protección de main, las pruebas y la fusión manual de la PR de versión se
mantienen. GHCR sigue autenticándose con el token del job de publicación.

## Fuentes técnicas

- [uv](https://docs.astral.sh/uv/guides/projects/).
- [FastAPI](https://fastapi.tiangolo.com/).
- [SQLAlchemy y SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html).
- [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html).
- [aiolimiter: algoritmo](https://aiolimiter.readthedocs.io/en/stable/).
- [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk).
