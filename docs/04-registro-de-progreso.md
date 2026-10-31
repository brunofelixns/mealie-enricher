# Registro de decisiones y progreso

Las fechas se expresan en Europe/Madrid. Este registro describe hechos y decisiones; las tareas previstas están en el plan.

## 2026-10-28: exploración inicial

- Se solicitó examinar mealie-calorie-estimator para una migración a Python, considerando uv y FastAPI.
- Se revisaron README, dependencias y módulos de la referencia 1.12.3.
- Se identificaron Fastify, OFF, fallback LLM, SQLite mediante sql.js, cola por slug, etiquetas e historial.
- Se plantearon alternativas de agentes y opciones adicionales de infraestructura.
- Evidencia: lectura estática. No hubo ejecución ni implementación.

## 2026-10-29: corrección de alcance

- El usuario aclaró que la migración debía mantener las mismas funcionalidades y limitaciones.
- Las mejoras internas quedaron subordinadas a la equivalencia.
- Se presentó una alternativa ligera con sqlite3 y cliente LLM HTTP.
- La carpeta local se comprobó vacía antes de comenzar la documentación.

## 2026-10-29: selección vigente

- El usuario adjuntó la propuesta inicial y la seleccionó como base.
- Eligió explícitamente OpenAI Agents SDK para la IA.
- Solicitó crear docs y documentar el proceso.
- Solicitó un plan de implementación antes de empezar a migrar.
- Se retomaron SQLAlchemy/Alembic y Tenacity del adjunto; los extras opcionales permanecen fuera del alcance inicial.
- Se propuso conservar los límites con asyncio, dejando constancia de la diferencia entre la política original y aiolimiter.
- Se redactaron alcance, arquitectura, matriz de compatibilidad y plan de tareas.

## Situación histórica al entregar la documentación inicial

| Elemento | Estado |
|---|---|
| Alcance y decisiones | Documentados |
| Arquitectura | Propuesta escrita para revisión |
| Agents SDK | Elegido; integración pendiente |
| Plan de implementación | Redactado para revisión |
| Código Python | Sin implementar |
| Dependencias | Sin instalar ni resolver |
| Referencia ejecutable local | Sin descargar ni ejecutar |
| Pruebas de aplicación | Sin ejecutar |
| Contenedores | Sin construir ni iniciar |
| Servicios externos | Sin llamadas funcionales |
| Credenciales | Sin crear, leer ni modificar |
| Git | No se ha inicializado ni creado un commit |

Disponibilidad observada de herramientas: uv, Python 3.13, Node y npm aparecen en PATH. Esto no acredita versiones completas, compatibilidad ni disponibilidad de Python 3.14. Se comprobará al ejecutar el plan.

## 2026-10-29: verificación de la documentación

- Se comprobaron los siete archivos Markdown, sus enlaces locales, codificación y bloques de código.
- La copia del adjunto coincide byte por byte con el archivo aportado.
- La matriz contiene C01-C40 y el plan contiene nueve tareas, de 0 a 8.
- Todas las casillas de implementación permanecen pendientes.
- Una revisión técnica independiente no identificó preguntas importantes pendientes para poder planificar la ejecución.
- Se comprobó que la única carpeta creada en la raíz es docs.
- Evidencia: comprobaciones locales de archivos con Python, resultado correcto. No son pruebas de la aplicación.
- La revisión del usuario y el inicio de la implementación siguen pendientes.

## Hito histórico siguiente a la planificación

La ejecución autorizada comenzó con la captura de la referencia. El estado final se encuentra en el documento 06.

## Plantilla de futuras entradas

~~~text
Fecha:
Tarea y objetivo:
Decisión o cambio:
Archivos afectados:
Comando de verificación:
Resultado observado:
Tipo de evidencia: estática / simulada / local / proveedor real
Limitaciones o pendientes:
Siguiente paso:
~~~

Solo se marcarán tareas completadas después de registrar su evidencia. Un bloqueo de credenciales o proveedor no convierte una prueba simulada en una verificación real.

## 2026-10-29: inicio autorizado y fase 0 completada

- El usuario autorizó ejecutar el plan desde la fase 0 y mantener la documentación actualizada.
- Referencia descargada y fijada sin cambios en fuentes; typecheck correcto y 140 pruebas en 16 archivos aprobadas.
- Se generaron 110 capturas y una caché SQLite heredada. Dos capturas consecutivas produjeron los mismos hashes para los 112 artefactos.
- Vitest y las conexiones locales requirieron ejecución fuera del sandbox por errores EPERM/EACCES del entorno. No se atribuyeron esos errores al original.
- Fase 1 iniciada. Los siguientes resultados se detallan en el documento 06.

## 2026-10-29: fases 1–6 verificadas y fase 7 integrada

- Proyecto uv/Python 3.14, Agents SDK, reglas numéricas compatibles, SQLite/Alembic, cola e integraciones implementados en src/mealie_enricher.
- Verificaciones acumuladas: 7 → 28 → 94 → 102 → 123 → 157 pruebas aprobadas. Ruff y mypy correctos al cierre de cada fase. Comandos y alcance en el documento 06.
- Historial web/tema/seeding integrado con 162 pruebas aprobadas; revisión visual en curso. Nueva captura de desarrollo eleva el total a 111 casos sintéticos.
- No se han usado credenciales reales ni modificado un servidor Mealie existente. Docker Desktop no estaba activo; se está comprobando su arranque antes de la fase 8.

## 2026-10-29: fase 7 verificada y empaquetado local

- Historial HTML idéntico a la referencia, tema y 28 datos sintéticos compatibles. Revisión visual de claro/oscuro y estados realizada en servidor local de prueba.
- 165 pruebas aprobadas tras añadir entrypoint y mock OFF Python; Ruff/mypy correctos.
- Imagen local construida, Compose válido y Docker operativo. Mealie de prueba está separado por proyecto/volúmenes; la integración real se verificará antes del cierre.

## 2026-10-29: cierre de la migración local

- Fases 0–8 completas con evidencia. Suite final: 187 pruebas aprobadas y 2 Docker opt-in omitidas; ejecución Docker separada: 2 aprobadas en 42.17 s. Cobertura: 95 %. Ruff y mypy correctos.
- Revisión independiente completada y siete clases de regresión corregidas mediante pruebas RED→GREEN, incluyendo la recuperación de caché malformada. Sin hallazgos pendientes aplazados.
- Oráculo final: 125 casos/127 artefactos, repetición sin diferencias y fuentes upstream intactas.
- Imagen final inspeccionada: Python 3.14.6, Agents SDK 0.24.0, uid 1000, sin Node ni pytest. Contenedores y volúmenes de prueba retirados.
- Manual de operación/retorno y resoluciones de ejecución añadidos. Proveedor LLM real, CI remoto y publicación continúan sin ejecutar; no se han usado claves reales ni una instancia Mealie existente.
- El destino sigue sin Git; no se han creado commits, ramas ni remotos. Se conserva el ledger local para no perder evidencia.

## 2026-10-29: despliegue independiente desde GitHub Container Registry

- Solicitud: disponer de un apartado Docker con Compose y ejemplo de variables para descargar y ejecutar una imagen ya publicada.
- Añadidos docker/docker-compose.yml, docker/.env.example y docker/README.md. README principal e índice de documentación enlazan la instalación.
- Compose utiliza exclusivamente image configurable mediante MEALIE_ENRICHER_IMAGE, sin build ni referencias al código fuente. Incluye healthcheck Python, puertos configurables y volumen persistente.
- .env.example cubre las 30 variables de configuración de la aplicación. env_file carga también los tokens dinámicos por hogar; el único override de configuración es PORT para mantener coherencia con el puerto destino.
- La referencia ghcr.io/tu-usuario-o-organizacion/mealie-enricher:latest es un marcador que debe sustituirse por el paquete/tag publicado. No se atribuye un propietario GitHub sin conocerlo.
- Verificación: Compose válido; arranque aislado con solo los tres archivos copiados, puerto interno 8123 y puerto externo libre; GET /health correcto; token exclusivo por hogar conservado.
- Persistencia verificada tras docker compose down y up: el marcador dentro del volumen sigue presente. El proyecto de prueba y sus volúmenes se retiraron al finalizar.
- Comprobación estática: ninguna variable de configuración ausente y enlaces Markdown correctos. No se modificó código de aplicación ni se repitió su suite.
- Alcance de la evidencia: imagen local existente usada con --pull never para el ensayo. No se publicó ni descargó una imagen remota; la comprobación de GHCR queda pendiente de la publicación real.

## 2026-10-29: etiquetas automáticas en español y consulta del historial

- Solicitud del usuario: etiquetas en español para su Mealie y confirmación de que existe una vista web de actividad.
- Registrada D07 como adaptación autorizada de los nombres originales. Se mantienen umbrales, cálculos y reglas de datos manuales.
- Modificado services/tagging.py para crear las ocho etiquetas españolas y detectar las asociaciones inglesas registradas por el estimador.
- Si el hash no cambia, webhook/backfill actualizan solo tags/extras usando nutrientes existentes. Se conservan las etiquetas personales, el hash y los extras ajenos; la próxima ejecución vuelve a omitirse.
- Pruebas previas al cambio: 23 fallos observados (21 fronteras de etiquetas y 2 escenarios de sustitución). Suite posterior: 189 aprobadas y 2 Docker opt-in omitidas; Ruff y mypy correctos.
- Las capturas originales permanecen intactas. Las expectativas de equivalencia aplican solo la correspondencia autorizada de nombres/slugs de etiquetas.
- Vista web confirmada en las rutas/plantilla y sus pruebas: /estimator/history, filtros, estados, cambios, nutrientes, errores y polling cada 2 s. No se añadió otro frontend.
- Añadido docs/09-etiquetas-y-vista-web.md y actualizadas las guías. Imagen Docker local reconstruida; E2E con Mealie de prueba: 2 pruebas aprobadas en 51.53 s, incluidos los nombres españoles guardados por Mealie.

## 2026-10-29: publicación solicitada y presentación del repositorio

- El usuario solicita subir el proyecto a brunofelixns/mealie-enricher y un README visual con imagen representativa y logo de Mealie.
- Remoto comprobado vacío y privado; acceso de escritura confirmado. Esta solicitud autoriza inicializar Git y subir el código a main; no cambia la visibilidad ni publica una imagen en GHCR.
- Portada generada con la herramienta integrada; logo oficial descargado y verificado contra su blob de origen. Recursos, atribución, licencia del logo y prompt guardados en docs/assets.
- README reorganizado con presentación, navegación, instalación Docker, vista de actividad, etiquetas, configuración, API, desarrollo y créditos.
- Primera publicación en preparación: comprobar índice, enlaces, calidad y pruebas antes de subir.
- Verificación previa a la subida: 189 pruebas aprobadas, Ruff/mypy correctos, 237 archivos preparados sin patrones de credenciales ni archivos locales excluidos. README renderizado mediante GFM de GitHub con portada y logo. Se conservan los espacios finales heredados de NOTICE.
- Publicación completada: commit de código e7e737507553be41913704167c04fb10407fe4dd en main. Rama remota, README, código, Compose e imágenes verificados por hash. El repositorio conserva la visibilidad privada; GHCR sigue sin publicación.

## 2026-10-31 — Catálogos DuckDB y BEDCA

- El usuario aprueba SQLite exclusivamente para caché y DuckDB para catálogos persistentes. Se abre la rama local `codex/duckdb-catalogs` y se documenta el diseño y plan en el documento 11 y `docs/superpowers/plans/2026-10-31-catalogos-duckdb.md`.
- Base previa comprobada: 189 pruebas correctas, 2 Docker omitidas. Configuración opcional conserva exactamente el volcado heredado y el comportamiento con catálogo desactivado.
- Importador BEDCA, lector solo lectura y CLI implementados con pruebas primero. Exportación real descargada únicamente en carpetas ignoradas: 957 alimentos, 31.166 valores y 69 combinaciones; W=30.888/WKG=257/VM=15/D=6. Los 21 registros VM/D se preservan sin conversión a masa; 8.294 valores derivados disponibles en los campos actuales.
- Preparados esquema y tablas vacías para productos, nutrición propia por producto, presentaciones, tiendas y precios fechados. No hay recopiladores ni precios reales de supermercados en esta fase.
- Decisions se integra mediante el SDK oficial de OpenAI; Agents SDK conserva su adaptador original. La clave existente se reutiliza por autorización expresa del usuario, sin mostrarla ni guardarla en archivos. Una única prueba sintética real recibe AuthenticationError; no se declara validado el proveedor real.
- Implementados caché contextual, migración SQLite 0002, hash contextual/versionado y composición de FastAPI. El catálogo se prepara aparte y se monta en solo lectura; no se descarga en cada inicio.
- Primera suite completa: 290 correctas y 2 omitidas. Revisión independiente detecta tres P2: alias cocido/hervido, genérico que oculta estados y estimación anterior cuando faltan ingredientes evaluables. Corregidos con regresiones; se conserva explícitamente la suma parcial heredada C22.
- Se verifica recuperación de fallo de Decisions sin esperar a la caducidad de caché. La prueba Docker del Compose de despliegue importa CSV sintéticos, arranca FastAPI, consulta el catálogo y comprueba volúmenes separados y permisos de solo lectura: 1 correcta en 38,53 s.
- La construcción local de la imagen 1.13.0 funciona y contiene DuckDB 2.0.0. La comprobación de tipos completa queda correcta para 45 archivos. Verificación final repetida tras ajustes de revisión: pendiente de registrar el cierre.
- Cierre de verificación: 318 pruebas ordinarias correctas y 3 Docker omitidas en esa ejecución; Ruff y mypy correctos. Docker opt-in: 3 correctas en 112,58 s, incluyendo Mealie real v3.19.2 aislado y borrado efectivo de nutrición anterior cuando pasa a desconocida.
- Se conservan CSV externos en `data/bedca/` y catálogo preparado en `data/catalogs/catalogos.duckdb`, todos ignorados por Git. No se cambia la configuración real del usuario ni se publica imagen. La activación del catálogo y la configuración de una clave OpenAI aceptada se documentan en el documento 11.
