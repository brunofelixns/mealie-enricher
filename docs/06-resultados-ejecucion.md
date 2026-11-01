# Resultados de ejecución

## Resultado observado al cerrar la migración inicial

| Verificación | Resultado |
|---|---|
| Referencia upstream | 140 pruebas aprobadas; fuentes sin cambios |
| Capturas finales | 125 casos C01–C40; 127 artefactos repetidos sin diferencias |
| Suite Python ordinaria | 187 aprobadas, 2 omitidas por Docker opt-in; sin warnings |
| Cobertura | 95 % de 1348 sentencias; 62 sin ejecutar |
| Ruff | Check correcto; 71 archivos con formato correcto |
| mypy | 36 archivos sin incidencias |
| uv sync --locked --offline | Correcto; lockfile reproducible |
| Docker Compose | Configuración válida e imagen construida localmente |
| E2E Docker separado | 2 pruebas aprobadas en 42.17 s |
| Runtime de imagen | Python 3.14.6, uid 1000, Agents SDK 0.24.0; sin Node ni pytest |
| Interfaz | HTML idéntico, claro/oscuro y polling revisados en navegador |
| LLM real / CI remoto / publicación de imagen | Sin ejecutar; no equivalen a las pruebas locales |

Las secciones siguientes conservan la secuencia de avance. Los recuentos anteriores pertenecen a cada fase, no al estado final.

## Fase 0 — completada el 2026-10-29

| Comprobación | Resultado |
|---|---|
| Referencia | c2dc71a1d8effe29375391f2fe50da94d27cfd7d, versión 1.12.3 |
| Fuentes upstream | Sin modificaciones en archivos controlados |
| npm ci | 178 paquetes instalados desde el lockfile |
| npm run typecheck | Correcto |
| npm test | 140 pruebas aprobadas, 16 archivos |
| Capturador | 110 casos, contratos C01-C40 identificados |
| Repetición | 112 artefactos comparados, ningún hash diferente |
| Proveedor real de IA | Sin llamadas |

Herramientas observadas en fase 0: Node 22.23.1, npm 11.6.0, uv 0.11.28, Git 2.55.0.windows.3 y Python 3.14.6. La resolución Python se completó en fase 1.

Las capturas utilizan las funciones y rutas originales, un servidor Mealie local simulado y respuestas OFF/LLM sintéticas. El capturador comprueba los estados de cada flujo para impedir que un error de infraestructura se guarde como resultado válido.

Los primeros intentos de Vitest fallaron antes de ejecutar pruebas por restricciones EPERM sobre temporales. Las conexiones locales del capturador también fueron denegadas por el sandbox. Las ejecuciones con permisos adecuados pasaron; las fuentes originales no se modificaron para evitarlos.

Comandos reproducibles:

~~~powershell
git -C .reference/mealie-calorie-estimator rev-parse HEAD
Push-Location .reference/mealie-calorie-estimator
npm.cmd run typecheck
npm.cmd test
Pop-Location
node .reference/mealie-calorie-estimator/node_modules/tsx/dist/cli.mjs tests/reference/capture.mts
~~~

Artefactos: tests/reference/capture.mts, tests/fixtures/parity/manifest.json, los JSON de casos y legacy-cache.db. La copia upstream y los logs temporales se excluyen del control de versiones.

## Fase 1 — completada el 2026-10-29

Preparación de proyecto, modelos y configuración. Los resultados Python se añadirán después de ejecutar las pruebas correspondientes.

### Cierre de fase 1

- Python 3.14.6 y 71 paquetes resueltos en uv.lock; OpenAI Agents SDK 0.24.0.
- RED observado: faltaban config.py y models.py. GREEN: 7 pruebas aprobadas; Ruff correcto y mypy sin incidencias en 3 archivos.
- El caso de tokens usa identificadores sin colisión para evitar que Windows fusione variables que solo difieren por mayúsculas. Se conserva la comparación de casing sobre un mapping explícito.
- Incidencia local corregida: Ruff recorrió la caché porque todavía no hay repositorio Git. Se excluyeron .cache/.venv explícitamente y se acotaron los comandos a src y tests. Se reinstalaron todas las dependencias desde el lockfile sin caché. Auditoría de 5204 archivos Python de dependencias contra sus RECORD: ninguna diferencia.
- Se conservan LICENSE y NOTICE de la referencia. No se han leído ni utilizado credenciales reales.

## Fase 2 — completada el 2026-10-29

Pruebas escritas y RED observado por ausencia de la capa agents. Adaptador SDK implementado; verificación del Runner en curso.

### Cierre de fase 2

- OpenAI Agents SDK 0.24.0 utiliza Agent/Runner con un modelo adaptador HTTPX, sin herramientas, memoria ni delegación.
- RED observado por ausencia del módulo agents. GREEN: suite completa de 28 pruebas aprobada; Ruff correcto y mypy sin incidencias en 7 archivos.
- Las pruebas pasan por Runner real y verifican prompts/payload de los fixtures, endpoint personalizado, 429/500 sin reintentos, respuesta incompleta y ausencia de llamadas de tracing.
- Diagnóstico de entorno: el sandbox bloquea socketpair al inicializar asyncio en Windows. Las pruebas asíncronas se ejecutan con permisos adecuados y proveedores simulados. No fue necesario cambiar el SDK ni el comportamiento de la aplicación.

## Fase 3 — completada el 2026-10-29

Pruebas de hash, conversiones, nutrientes y etiquetas escritas antes de sus módulos. Verificación diferencial en curso.

### Cierre de fase 3

- RED observado por ausencia de compat y services. GREEN: 94 pruebas de la suite completa aprobadas; Ruff correcto y mypy sin incidencias en 12 archivos.
- Comparación de hashes, 16 casos de unidades, etiquetas en fronteras y patches nutricionales contra la referencia.
- Se mantienen redondeos .5 de JavaScript, orden UTF-16 en el hash, representación numérica y aproximaciones de unidades.
- Las etiquetas parciales aceptadas por el filtro original también se aceptan en el modelo migrado; no se añadió una validación de id que cambiase ese filtro.

## Fase 4 — completada el 2026-10-29

Pruebas de caché, migración heredada, cola, limitadores e historial escritas antes de sus módulos; implementación y comprobación en curso.

### Cierre de fase 4

- RED observado por ausencia de storage/runtime. GREEN: 102 pruebas de la suite completa aprobadas; Ruff correcto y mypy sin incidencias en 20 archivos.
- Alembic reconoce la base exportada por el original sin perder filas y añade la revisión 0001. Se verifica TTL, persistencia al reabrir y claves normalizadas.
- La cola serializa un slug y permite otros concurrentes; reinicia debounce, agrupa claves y continúa después de fallos.
- Límites independientes por ventanas de 60 s con esperas de 1 s. Historial con 200 entradas, 24 h, estados y truncado de errores.

## Fase 5 — completada el 2026-10-29

Clientes Mealie/OFF y fallback LLM implementados después de observar el RED de sus pruebas. Comparación de red y parsers en curso.

### Cierre de fase 5

- RED observado por ausencia de clients y llm_estimator. GREEN: suite completa con 123 pruebas aprobadas; Ruff correcto y mypy sin incidencias en 24 archivos.
- Mealie: paginación, tokens, subruta de URL, 204, errores HTTP, timeout, JSON inválido y creación de etiquetas con recuperación de existentes.
- OFF: primera coincidencia, kcal cero, ausencia de kcal, no coincidencia y cuatro intentos con esperas 500/1000/2000 ms.
- LLM: parser de gramos y nutrientes, ceros, fences, respuestas inválidas y una única llamada en errores, manteniendo el Runner SDK real.

## Fase 6 — completada el 2026-10-29

Pruebas de rutas y flujos completos escritas antes de app.py y processing.py. Comparación de historia y patches contra la referencia en curso.

### Cierre de fase 6

- RED observado por ausencia de app y procesamiento. GREEN: 157 pruebas aprobadas; Ruff correcto y mypy sin incidencias en 32 archivos. La suite posterior de 162 pruebas confirma esta fase integrada con historial.
- Dieciocho flujos completos comparan solicitudes, patches e historial con el original: webhook, estimate y backfill en seis estados cada uno.
- Diez casos HTTP comparan códigos, cuerpos, Content-Type y CORS; webhook y backfill simultáneos comparten serialización por receta.
- Se conservan las calorías manuales en webhook/backfill y se fuerza la estimación en estimate. Extras ajenos y etiquetas del usuario permanecen en los patches.

## Fase 7 — completada el 2026-10-29

- Se añadieron pruebas antes de implementar tema y datos de desarrollo; RED observado por ausencia de los módulos.
- Suite: 162 pruebas aprobadas. HTML idéntico byte por byte a la referencia; tema válido durante 2 h, fallback durante 30 s y colores inválidos sustituidos por los originales.
- Se añadió una captura del seeding original: ahora 111 casos. Los 28 registros coinciden tras normalizar sus UUID; reiniciar descarta el historial salvo seeding explícito.
- Revisión local en navegador iniciada: los siete estados y las 28 entradas aparecen y el polling funciona. Comprobación de claro/oscuro en curso.

### Cierre de fase 7

- 162 pruebas aprobadas; Ruff correcto y mypy sin incidencias en 34 archivos.
- Revisión visual local mediante navegador: tema oscuro y claro, 28 entradas, siete estados, enlaces y detalles nutricionales. Polling observado actualizando duraciones de registros running; recarga mantiene datos dentro del proceso.
- Las pruebas de reinicio acreditan historial vacío por defecto y seeding únicamente con DEV_SEED_HISTORY=true. No hay persistencia adicional.

## Fase 8 — completada el 2026-10-29

- RED de pruebas de entrypoint y mock OFF observado antes de crear sus módulos.
- 165 pruebas aprobadas; Ruff correcto y mypy sin incidencias en 36 archivos.
- Docker Desktop iniciado. docker compose config --quiet y construcción de la imagen mealie-enricher:local correctos; runtime Python 3.14.6 sin Node, usuario 1000 y dependencias de producción del lockfile.
- Prueba con Mealie v3.19.2 aislado en curso. CircleCI configurado; no se afirma ejecución remota de CI ni publicación de imágenes.

### Integración Docker observada

- E2E real: 1 prueba aprobada en 41.99 s con Mealie v3.19.2, OFF Python simulado y LLM deshabilitado.
- Receta sintética: 100 g de harina/2 raciones → 182 kcal/ración guardadas en Mealie; dos etiquetas y extras ajenos conservados. Un webhook posterior termina skipped por hash.
- Health, historial HTML/JSON y usuario appuser verificados en contenedor. Proyectos y volúmenes del E2E eliminados al terminar; el proyecto de consulta de OpenAPI también se retiró.
- Suite ordinaria previa a revisión: 165 aprobadas, 1 omitida (Docker opt-in), cobertura 95 %. uv sync --locked --offline correcto.
- Revisión final amplía el oráculo a 121 casos: errores de parsing HTTP, texto plano, Content-Type, preflight y cantidades/raciones numéricas como texto. Se observaron fallos antes de corregirlos; resultados del cierre pendientes.

### Revisión final y cierre de fase 8

Revisión independiente de código, solo lectura, seguida de una única pasada de correcciones. No hubo hallazgos críticos. Se corrigieron seis regresiones importantes: extras JSON arbitrarios, parsing HTTP, precedencia de token del perfil test, hashes con números como texto, deadline total y redirecciones fetch. Cada clase dispuso de una prueba que fallaba antes de la corrección y pasa en la suite final.

La tolerancia a JSON malformado en caché también se corrigió, reclasificando el hallazgo por su efecto: una fila recuperable no debe bloquear una receta. Los aliases de alimentos aceptan objetos y null, conservando la lectura del esquema real de Mealie.

Las capturas HTTP incluyen JSON inválido/vacío, media type no admitido, texto plano, cuerpos null/ausentes, preflight inválido, HEAD y ruta inexistente. Las pruebas de transporte cubren 307/308 del LLM con el mismo payload, 302 de OFF, 301 del tema y cuerpos que llegan lentamente. Mealie conserva una única escritura y no sigue redirecciones.

Comandos de cierre efectivamente ejecutados:

~~~powershell
uv sync --locked --offline
.venv/Scripts/ruff.exe check src tests alembic
.venv/Scripts/ruff.exe format --check src tests alembic
.venv/Scripts/mypy.exe src
.venv/Scripts/python.exe -m pytest --cov=mealie_enricher --cov-report=term-missing --cov-report=xml -q
docker compose config --quiet
docker compose build calorie-estimator
$env:RUN_DOCKER_SMOKE = '1'
.venv/Scripts/python.exe -m pytest tests/integration/test_docker_smoke.py -q
~~~

Resultado: 187 pruebas ordinarias y 2 Docker aprobadas; las dos pruebas Docker se omiten únicamente en la ejecución ordinaria. No quedan correcciones de revisión aplazadas. No se ha desplegado sobre una instancia existente, publicado una imagen ni inicializado Git.

Los límites de la evidencia y todas las resoluciones de ejecución se recogen en el documento 08. La cobertura y los fixtures comprueban los casos descritos; no constituyen una prueba exhaustiva de todas las entradas inválidas posibles.

## Ampliación: instalación de imagen publicada en GHCR

Archivos de entrega: [docker-compose.yml](../docker/docker-compose.yml), [.env.example](../docker/.env.example) y [guía](../docker/README.md). Se pueden copiar a un servidor sin el resto del proyecto.

Verificación local del Compose de despliegue:

| Comprobación | Resultado |
|---|---|
| Configuración Compose | Válida; servicio sin build, image configurable y pull_policy=always |
| Variables | 30 variables de aplicación documentadas, ninguna ausente |
| Arranque independiente | Correcto con los archivos copiados y la imagen local existente |
| Puertos | Interno 8123 y puerto externo libre; health correcto |
| Hogares | Token cargado exclusivamente mediante .env, sin token general |
| Persistencia | Volumen conservado tras down/up |
| Limpieza | Proyecto aislado y volúmenes de prueba retirados |
| GHCR remoto | Sin comprobar: falta publicar el paquete real y configurar su dirección |

Para el ensayo se usó --pull never como override de la política de descarga, sin cambiar el Compose de entrega. Las instrucciones de instalación utilizan docker compose pull y up --no-build. Este avance afecta solo a empaquetado/documentación; los resultados anteriores de la suite corresponden al código de aplicación sin cambios.

## Ampliación: etiquetas en español (D07)

- Etiquetas de calorías: Calorías:Bajas, Calorías:Moderadas, Calorías:Altas y Calorías:Muy altas.
- Digestibilidad: Digestión:Fácil, Digestión:Moderada, Digestión:Lenta y Digestión:Desconocida.
- Los 21 casos de frontera conservan las clasificaciones originales y solo cambian sus nombres.
- Dos nuevas pruebas de webhook/backfill verifican la sustitución de asociaciones inglesas del estimador sin recalcular nutrición, contactar OFF/LLM o retirar etiquetas personales. Una ejecución posterior queda skipped.
- RED observado antes del código: 23 casos fallaban. Suite Python posterior: **189 aprobadas y 2 omitidas por Docker opt-in**, en 10.44 s. Ruff: 73 archivos con formato correcto; mypy: 36 archivos sin incidencias.
- Las grabaciones originales siguen intactas. El helper de expectativas aplica exclusivamente la traducción solicitada.
- Vista web existente confirmada mediante código y pruebas del historial: /estimator/history, actualización cada 2 s, filtros y detalle de las ejecuciones.
- Imagen local reconstruida con el cambio; **2 pruebas Docker aprobadas en 51.53 s**, con los nombres españoles devueltos por Mealie v3.19.2 y un webhook posterior omitido por hash. El entorno aislado se retiró al terminar.
- No se ha actualizado una instancia del usuario ni publicado una imagen remota.

## Publicación del código y README visual

Código publicado en [brunofelixns/mealie-enricher](https://github.com/brunofelixns/mealie-enricher), rama main. El commit de código e7e737507553be41913704167c04fb10407fe4dd se verificó contra la referencia remota.

README, código de aplicación, Compose de despliegue, logo y portada comprobados por hash en GitHub. README renderizado con la API GFM: 5 tablas y 7 imágenes. El índice incluía 237 archivos, sin archivos .env reales, entornos o cachés, y sin hallazgos de patrones de credenciales.

Comprobación previa a la publicación: 189 pruebas Python aprobadas en 11.22 s y 2 Docker opt-in omitidas; Ruff y mypy correctos. La ejecución Docker anterior permanece documentada en su apartado y no se repitió para este cambio de presentación.

Se conserva la visibilidad privada. Publicar el código no ha publicado una imagen en GHCR ni acredita una ejecución remota de CI. [Detalles y atribución](10-publicacion-github.md).

## 2026-10-31 — Versión 1.13.0: catálogos DuckDB

- `pytest -q --tb=short`: 318 correctas y 3 Docker omitidas, 69,95 s. Incluye la compatibilidad heredada y las regresiones de contexto, estado, unidades, caché, lectura, importación y limpieza de valores anteriores.
- Ruff correcto; 94 archivos con formato comprobado. Mypy correcto en los 45 archivos de fuente.
- `uv sync --locked --offline`: correcto; DuckDB 2.0.0 y OpenAI 3.41.0, Agents SDK 0.24.0. Versión de aplicación 1.13.0.
- Construida imagen local `mealie-enricher:catalog-1.13.0` y `mealie-enricher:local`. No se publica en GHCR ni se verifica ARM o CI remoto.
- BEDCA real importado localmente: 957 alimentos, 31.166 componentes originales, 69 combinaciones de unidad/base y 8.294 valores derivados. 21 componentes por volumen/materia seca quedan sin convertir. Los archivos reales están ignorados por Git.
- Resolución con DuckDB real, sin proveedor: Arroz permanece ambiguo; Arroz cocido encuentra bedca:2661 mediante alias hervido; Arroz integral crudo encuentra bedca:904. Esta comprobación verifica identidad/flujo, no certifica la exactitud nutricional de la fuente (véase la observación de 2661 en el documento 11).
- Una llamada sintética real de Decisions, autorizada por el usuario: AuthenticationError. El proveedor no se considera validado positivamente. El SDK/contrato HTTP y la abstención se prueban con transporte simulado; los fallos no se fijan en caché y no hay reintentos automáticos.
- Docker final: 3 pruebas correctas en 112,58 s. Incluyen Mealie v3.19.2 real aislado, flujo heredado, cambio a BEDCA, limpieza real de calorías al pasar a ambigüedad, importador del Compose de despliegue, permisos de appuser, lectura de catálogo y volúmenes separados. Se eliminaron únicamente los proyectos y volúmenes temporales propios.

## 2026-11-01 — Validación adicional de los flujos completos

- Añadidos 16 escenarios de integración en `test_catalog_workflows.py` y `test_catalog_operations.py`, sin cambios de producción.
- Suite completa con cobertura: 334 correctas y 3 Docker omitidas, 30,46 s. Cobertura de líneas 1.866/1.952 (95,59 %).
- Docker: 3 correctas en 75,51 s; Mealie real aislado, flujo heredado, BEDCA, borrado de valores anteriores e importación del catálogo con volúmenes separados.
- Ruff correcto; formato de 96 archivos comprobado; mypy correcto en los 45 archivos de producción.
- OpenAI se prueba mediante el SDK real con transporte interceptado y claves sintéticas. No se ha repetido la consulta real fallida por autenticación ni se ha utilizado ninguna clave personal en estas pruebas.
- [Matriz de escenarios y comandos](12-validacion-catalogos.md).

## 2026-11-01 — Ampliación de pruebas con Mealie real

- Nuevos escenarios HTTP en Docker: **14 correctos en 123,74 s**, con Mealie v3.19.2 real aislado, SQLite y DuckDB reales. Incluyen cambios crudo/cocido, raciones, etiquetas y datos personales, calorías manuales, ingredientes desconocidos o eliminados, backfill, errores, reinicios y sustitución del catálogo.
- BEDCA real local: 957 alimentos y 31.166 componentes importados en el volumen temporal; Mealie guarda 384 kcal y 8 g de proteína por ración, con referencia bedca:904. Los archivos externos no se incluyen en Git ni se modifican.
- Regresión Docker anterior: **3 correctas en 67,55 s**. Total: **17 pruebas Docker correctas** entre ambas ejecuciones.
- Suite ordinaria: **334 correctas y 17 Docker omitidas en 45,33 s**. Ruff/formato y mypy correctos; no hay cambios de producción.
- El primer intento falla en la infraestructura antes de procesar recetas: puerto no accesible desde Windows con red internal. La red propia normal de Compose con puertos en loopback resuelve el acceso; la ejecución posterior pasa completa.
- Los proyectos temporales propios se retiran al finalizar. No hay llamadas a OpenAI ni cambios en el Mealie del usuario, publicación de código o de imagen.
- [Escenarios, resultados y comandos](13-pruebas-mealie-real.md).
