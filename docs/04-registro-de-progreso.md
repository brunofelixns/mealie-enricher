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

## 2026-11-01 — Validación adicional solicitada

- El usuario solicita crear las pruebas necesarias para validar la ampliación. Se comprueba el estado local y se ejecuta una base fresca: 318 pruebas correctas, 3 Docker omitidas y cobertura de líneas 95,44 %.
- Se añaden 16 escenarios en dos archivos: flujo HTTP con SDK OpenAI real interceptado; abstención, rechazo, 401, 429 y timeout; recuperación sin esperar TTL; caché tras reinicio; cambio de nota; sustitución versionada del catálogo; fallo de publicación con archivo anterior intacto; liberación de DuckDB tras arranque incompleto; migración de las cuatro tablas heredadas; fallback a OFF; unidades sin masa conocida; y protección de calorías manuales.
- No se modifica el código de producción ni se usa ninguna clave personal o API OpenAI real. Los datos son sintéticos; Docker utiliza únicamente proyectos temporales aislados.
- Ejecución dirigida: 16 correctas. Suite completa: 334 correctas y 3 Docker omitidas en 30,46 s. Cobertura de líneas 95,59 %; Ruff y formato correctos. [Detalle y comandos](12-validacion-catalogos.md).
- Cierre: 3 pruebas Docker correctas en 75,51 s, con Mealie real aislado, y mypy correcto en 45 archivos. Todas las comprobaciones solicitadas quedan ejecutadas; la validación positiva del proveedor OpenAI en vivo continúa pendiente de una clave aceptada, como ya estaba documentado.

## 2026-11-01 — Pruebas ampliadas contra Mealie real aislado

- El usuario solicita más pruebas reales. Se añaden 14 escenarios HTTP con la aplicación, Mealie v3.19.2, SQLite y DuckDB reales en un proyecto Compose temporal con red, cuenta, puertos y volúmenes propios.
- Verificados crudo/cocido, raciones, cambio de nota y hash, migración de etiquetas, preservación de metadatos personales y calorías manuales, estimación explícita, masa desconocida, eliminación de ingredientes, suma parcial heredada, backfill, 404 y recuperación, reinicio y actualización explícita del catálogo.
- Se incorpora una prueba opcional con los CSV BEDCA reales locales: 957 alimentos y 31.166 componentes importados en el volumen temporal. Una receta de 200 g de arroz integral para dos raciones devuelve desde Mealie 384 kcal, 8 g de proteína y referencia bedca:904.
- Docker Desktop estaba detenido y se inicia para las pruebas. El primer intento de la nueva infraestructura falla antes de registrar la cuenta por el acceso al puerto desde una red internal; se sustituye por la red Compose propia normal con puertos en loopback. Ejecución posterior: 14 correctas en 123,74 s.
- Suite ordinaria: 334 correctas y 17 Docker omitidas en 45,33 s; Ruff y formato correctos; mypy correcto en 45 archivos. No se modifica producción ni se consulta OpenAI. [Detalle reproducible](13-pruebas-mealie-real.md).
- Regresión de los tres escenarios Docker anteriores: 3 correctos en 67,55 s. Total Docker en ambas ejecuciones: 17 correctos. Confirmada la retirada de los proyectos temporales propios; no se publica código ni imagen.

## 2026-11-01 — Variante Docker con BEDCA y CSV incluidos

- El usuario solicita arrancar con DuckDB ya preparado y conservar los CSV. Confirma distribución pública no comercial. Se consulta el documento oficial de condiciones BEDCA y se registra D13; los datos mantienen su atribución y condiciones propias.
- Se prepara `docker/Dockerfile.bedca`: los tres CSV se suministran por contexto BuildKit explícito y el catálogo se valida/genera durante build. Los originales se conservan sin cambios junto al manifiesto y aviso de uso en `/opt/bedca`, fuera del volumen externo.
- La variante activa BEDCA por defecto. Ambos Compose aceptan la ruta de `.env`, conservando el valor anterior como fallback. Se añade `.env.bedca.example` y se mantiene la imagen base sin datos. SQLite y el código de estimación no cambian.
- Pruebas previas al cambio muestran las dos rutas Compose forzadas al volumen; tras corregirlas pasan. La primera ejecución de empaquetado valida CSV/permisos/datos inválidos y arranque; la comprobación de actualización detecta que el helper de pruebas aún consultaba la ruta antigua. Se corrige únicamente ese helper.
- Construcción local con BEDCA real correcta: 957 alimentos, 31.166 componentes, 8.294 valores derivados, CSV originales y 21 componentes sin conversión a masa. Se prepara la suite completa con Mealie real y actualización entre imágenes. [Operación y resultados](15-imagen-con-bedca.md).
- Cierre: 358 pruebas correctas sin omisiones en 402,68 s, incluidas 24 Docker y 7 escenarios nuevos de la variante. Arranque sin importación, cambio de imagen 360→400 kcal conservando SQLite y Mealie con BEDCA real 384 kcal/8 g de proteína/bedca:904 verificados. Ruff/formato/mypy correctos y revisión independiente sin hallazgos. Se retiran los proyectos temporales y se conserva la imagen local real; no se publica la nueva variante en GHCR.

## Versión propia 1.0.0 — corrección de numeración

- El usuario establece 1.0 como versión correcta del proyecto. Se normaliza como 1.0.0 en pyproject, uv.lock, imagen base y variante BEDCA; no cambia el comportamiento ni las dependencias.
- Se actualizan presentación, guías y nombres de imágenes de prueba. Se conserva la numeración antigua en las evidencias históricas y la versión 1.12.3 del proyecto original.
- El ejemplo de despliegue público sigue utilizando un artefacto existente mediante latest. Se distingue expresamente la versión del código local de la imagen publicada anteriormente; no se declara publicado un tag 1.0.0 por cambiar los metadatos.
- Verificación final: 334 pruebas ordinarias correctas (24 Docker omitidas) en 47,27 s; 3 comprobaciones Docker dirigidas correctas en 45,20 s, incluido Mealie real con la variante 1.0.0 y BEDCA. Paquete y etiqueta OCI coinciden en ambas imágenes; Ruff/formato y enlaces locales correctos. Se conservan las imágenes locales y se guarda el ajuste sin publicación.

## 2026-11-02 — GitHub Actions y versiones automáticas

- El usuario solicita ejecutar toda la suite en cada subida y actualizar GHCR después de pasarla, con versión automática. Se registran diseño/plan y D15.
- Workflow de lectura para ramas/PR y publicación dependiente solo en main propietario. Se fijan acciones y exportación BEDCA por revisión, con checksums; el token de publicación es GITHUB_TOKEN, sin añadir PAT.
- Se implementan versiones reproducibles, exclusión/reserva de v1.13.0, commit/tag atómico, recuperación de reintentos y protección frente a pushes concurrentes. Se añaden 28 pruebas Git reales en repositorios temporales y 10 pruebas de informe/promoción.
- Calidad local correcta; suite ordinaria: 372 correctas y 24 Docker omitidas en 165,32 s. Actionlint correcto. La revisión independiente detecta la descarga necesaria de Mealie/OFF para runners vacíos y se corrige; sin otros hallazgos.
- Se prepara la activación y verificación real de Actions y GHCR. [Flujo y operación](16-github-actions.md).
- Activado en main mediante 7ec463e. Actions ejecuta desde cero calidad, BEDCA y las 396 pruebas, todas correctas y sin omisiones (pytest 196,34 s; job 4 min 46 s). El primer push GHCR falla por permiso write_package del paquete; su configuración no contiene ningún repositorio en Manage Actions access. Se prepara la concesión Write solo a mealie-enricher y se solicita la confirmación que exige la política del navegador. No se cambian tags estables ni referencias de versión tras el fallo.
- El usuario autoriza expresamente el permiso: aplicado Write solo a Actions de brunofelixns/mealie-enricher sobre su paquete GHCR y reintentado el job fallido. La validación correcta se conserva; la alternativa comentada de main protegida y Release Please todavía no se ha implementado.
- El segundo intento confirma que GHCR acepta el push. Falla después al descargar ARM usando el mismo digest de índice ya asociado a amd64 en Docker 28/overlay2. Corregida la selección de manifiestos por arquitectura, con tres regresiones observadas antes del cambio y siete pruebas de publicación correctas después. Los tags estables siguen intactos en este punto; se prepara una nueva validación completa y publicación.
- Verificación de la corrección: candidato GHCR real ejecutado correctamente en amd64 y arm64 mediante los manifiestos específicos; versión 1.0.0 y usuario 1000 comprobados. Suite local 375 correctas/24 Docker omitidas en 164,53 s; calidad/YAML correctos y revisión independiente sin hallazgos. Se conserva el alcance de aplicación y se repite Actions para validar los 399 escenarios antes de la publicación estable.
- Actions 41449216230 valida la revisión 2265d33: 399 pruebas correctas, ninguna omitida, en 200,39 s; job completo 4 min 49 s. Comienza la publicación dependiente con todos los escenarios Docker, BEDCA real y Mealie aislado correctos.
- Publicación completada en 3 min 29 s: v1.0.0 y los cinco tags estables base/BEDCA publicados. Verificados anónimamente los índices GHCR y sus cuatro manifiestos hijos; ambos soportan amd64/arm64. Actions ejecuta ambas variantes/arquitecturas, con versión 1.0.0, usuario 1000 y BEDCA con 957 alimentos/tres CSV. Tag y main coinciden en 2265d33 y GitHub confirma 1.0.0 como release vigente. Digests y enlace de release registrados en el documento 16; ARM mediante QEMU, sin SBOM/provenance. Main protegida y Release Please siguen pendientes.

## 2026-11-02 — Main protegida y Release Please

- El usuario aprueba aplicar el modelo de PR obligatorias y PR de versión. Se crea la rama codex/release-please, con diseño/plan y D16 que sustituye el disparador de D15.
- Se elimina el helper que generaba commits/push directos a main y sus pruebas obsoletas. El nuevo helper solo consulta Git y valida metadatos/tag/ancestría/política de aliases.
- Release Please SDK 17.11.2 fijado con npm lock, únicamente en CI. El SDK oficial actualiza pyproject, uv.lock y Dockerfile; la prueba real detecta que su parser TOML envuelve los valores y se ajusta el selector para cambiar solo el paquete propio. La aplicación y las dependencias Python no cambian.
- El gestor usa GITHUB_TOKEN y lanza explícitamente CI para su PR y sus releases. No hay PAT nuevo ni auto-merge. La publicación exige un tag publicado, suite exacta y metadatos consistentes; los reintentos antiguos no retroceden aliases.
- Pruebas dirigidas: política Git 20 correctas, promoción 8 correctas y SDK real 2 correctas. Se prepara validación completa, revisión y activación mediante PR.
- Protección de main aplicada y verificada por API, incluidos administradores y suite obligatoria con rama actualizada. Actions permite crear PR con el token, manteniendo permisos generales read; no se crean secretos.
- La revisión detecta y se corrigen cinco casos antes de integrar: validador del tag ejecutado antes de verificar confianza, job obligatorio omitido si falla su dependencia, eventos de CI manual que no satisfacen el check de PR, publicaciones pendientes canceladas por concurrencia y versión calculada antes de crear una release pendiente. Se añaden regresiones de Git/SDK/procedencia. La cola max está documentada por GitHub pero actionlint 1.7.12 requiere excluir únicamente el diagnóstico de esa propiedad nueva.
- Se consulta la elección entre GitHub App (CI de PR automático) y GITHUB_TOKEN (requiere aprobar CI de la PR del bot); se continúa el trabajo independiente mientras se espera la respuesta.
- Abierta la PR de implantación #1. Su ejecución 41455507265 pasa 394 pruebas Python sin omisiones (164,49 s) y 10 pruebas Node; confirma en GitHub que queue:max es válido. Las observaciones automáticas adicionales se reproducen antes de corregir: rama del SDK por defecto con componente, pérdida de un dispatch fallido, propuesta calculada con main avanzado y concurrencia push/PR. Configurada rama común, reconciliación con recibo GHCR, control de revisión y CI que valida la versión propuesta contra su base. Nuevas pruebas del SDK: 14 correctas; suite completa en comprobación antes de actualizar la PR.
- PR #1 integrada mediante squash dbdab01 tras 396 pruebas Python sin omisiones (189,66 s) y 14 Node correctas. Main sigue protegida. El gestor real finaliza en 25 s y crea PR #2, chore(main): release 1.0.1, modificando solo manifest, CHANGELOG, Dockerfile, pyproject y versión propia de uv.lock.
- Revisado su diff y aprobada la ejecución pull_request 41458779207 con las credenciales existentes del mantenedor, sin secretos nuevos. La prueba detecta una fixture Node fijada a 1.0.0; se prepara PR de corrección usando la versión del manifest para que los incrementos automáticos sigan siendo verificables.
- Dependabot señala GHSA-g3hv-75wg-m249 en minimatch 10.2.6, dependencia exclusiva del SDK de CI. Se fija minimatch 11.0.4 para su consumidor git-file-utils y se valida su compatibilidad con las pruebas del SDK; la aplicación y sus dependencias Python no cambian.
