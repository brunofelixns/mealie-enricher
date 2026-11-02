# GitHub Actions: PR obligatorias, Release Please y GHCR

## Flujo vigente

1. Trabajar en una rama y abrir una PR hacia main.
2. Pasar **Suite completa y calidad** con la rama actualizada respecto a main.
3. Fusionar la PR: el código entra en main, sin publicar una imagen nueva.
4. Release Please abre o actualiza una PR con versión, CHANGELOG y metadatos.
5. Fusionar esa PR decide publicar: se crea el tag/release y se lanza una
   validación completa de ese commit antes de publicar las imágenes en GHCR.

La PR de versión acumula notas y metadatos; las funcionalidades ya entraron
por sus propias PR. El bot no fusiona su PR ni escribe directamente en main.
La protección exige PR y CI también al administrador, sin exigir un segundo
revisor humano en este repositorio personal. No permite force push ni borrado.

## Comprobaciones de calidad y seguridad

La suite completa se ejecuta en `pull_request`, pushes a `main` y ejecuciones
manuales. Los pushes a ramas no repiten la validación de una PR. El nombre del
check obligatorio **Suite completa y calidad** y el rechazo de tests omitidos
se conservan. La cobertura de `src/mealie_enricher` debe alcanzar el **95 %**;
la referencia ordinaria medida antes de esta ampliación es **95,59 %**.
El resumen de Actions muestra cobertura y número de escenarios.

[quality.yml](../.github/workflows/quality.yml) ejecuta actionlint **1.7.12**
(archivo descargado con SHA-256 comprobado) y zizmor **1.31.1**, incluyendo
acciones compuestas y configuración de Dependabot. Solo se excluye en actionlint
el diagnóstico concreto de `concurrency.queue`, que esa versión no conoce.
Las excepciones de zizmor están junto a cada uso y justifican el checkout exacto
del tag y la App de un solo repositorio. Los títulos de PR siguen los tipos
Conventional Commits del proyecto, con scope y `!` opcionales, descripción
iniciada en minúscula y sin punto final. El evento `edited` vuelve a comprobarlos.
Dependency Review rechaza vulnerabilidades nuevas HIGH/CRITICAL, también en
dependencias de desarrollo o de ámbito desconocido; no escribe comentarios.

[security.yml](../.github/workflows/security.yml) analiza Python y Actions con
CodeQL `security-extended` en PR, `main` y semanalmente. Además, cada martes a
las **05:23 UTC** resuelve una vez los aliases `latest` y `bedca`, selecciona
sus manifiestos amd64/arm64 y ejecuta el mismo escáner que la publicación.
La base de vulnerabilidades de Trivy se actualiza; no se utiliza un resultado
anterior como aprobación. Los informes completos duran 90 días en Actions.
Se suben SARIF con cuatro categorías estables a Code Scanning para deduplicar
hallazgos y aprovechar sus alertas, sin crear issues o comentarios repetidos.

[compatibility.yml](../.github/workflows/compatibility.yml), cada miércoles a
las **05:41 UTC** o manualmente, consulta la release estable oficial de Mealie
y ejecuta toda la suite en proyectos Docker aislados con esa imagen. Las PR
conservan la versión fijada en Compose. No accede a una instalación personal,
no llama a proveedores LLM y no publica imágenes.

### Actualizaciones de dependencias

Aquí no existía `renovate.json`: la referencia a Renovate correspondía a
mealie-mcp-server. Se mantiene un único bot, **Dependabot**, con actualizaciones
semanales agrupadas de Actions, uv (también dependencias indirectas), npm del
SDK de release, Dockerfiles y Compose. Las versiones nuevas esperan siete días;
las actualizaciones de seguridad conservan el tratamiento propio de GitHub.
Las PR se revisan y pasan CI; no hay automerge ni credenciales nuevas.

El pin de Trivy está en [ci/trivy/Dockerfile](../ci/trivy/Dockerfile), incluyendo
versión y digest, y queda cubierto por el gestor Docker de Dependabot. El helper
Python consume ese pin; evita incrustar un digest fuera del alcance del bot.
El gestor Actions incluye explícitamente las carpetas de las acciones compuestas;
así mantiene también el SHA de `actions/attest`, no solo los workflows.
Esto traslada las mejoras de mantenimiento propuestas para Renovate sin activar
un segundo servicio. El refresco de uv.lock lo realizan sus PR de actualización;
no se programa una regeneración ciega del lock ni se cambian los metadatos de versión.

## GitHub App para CI sin aprobación adicional

Release Please utiliza la App privada y dedicada **Mealie Release brunofelixns**
(`mealie-release-brunofelixns`). Su registro e instalación se completaron tras
la confirmación expresa del usuario, con los permisos exactos descritos aquí.

| Configuración de Actions | Uso |
|---|---|
| Variable RELEASE_APP_CLIENT_ID | Client ID público de la App |
| Variable RELEASE_APP_SLUG | Identidad esperada del bot |
| Secreto RELEASE_APP_PRIVATE_KEY | Clave privada de la App |

La App está instalada solo en brunofelixns/mealie-enricher. Contents, Pull requests
e Issues tienen escritura; Metadata, lectura implícita. No recibe permisos
de administración, workflows, paquetes, cuenta ni organización, ni webhooks.
La acción oficial create-github-app-token v3 está fijada por SHA; solicita
únicamente esos tres permisos y ese repositorio. El token caduca como máximo
en una hora y se revoca al finalizar el job. No se guarda la clave en Git,
archivos .env, la imagen Docker ni logs.

El SDK crea/actualiza PR y releases con esa identidad. Los eventos de la App
inician el CI normal de pull_request sin aprobación del mantenedor. El token
GITHUB_TOKEN del gestor queda en lectura más Actions write para solicitar la
publicación; GHCR conserva el token de su propio job. No hay fallback silencioso
al token anterior si la App no está configurada.

La procedencia de releases reconoce solo la App configurada y el bot anterior
github-actions[bot]. Esto permite continuar la PR existente y reintentar releases
anteriores durante la transición. Otros bots y autores humanos se rechazan;
la rama de la PR debe pertenecer también a este mismo repositorio.
La creación/aprobación de PR mediante GITHUB_TOKEN está deshabilitada en la
configuración general del repositorio; sus permisos por defecto son de lectura.

## Workflows y permisos

- [ci-release.yml](../.github/workflows/ci-release.yml): pushes, PR y ejecución
  manual. Resuelve la revisión, valida metadatos, ejecuta los tests del SDK,
  Ruff, formato, mypy y toda la suite Python/Docker sin omisiones.
- [release-please.yml](../.github/workflows/release-please.yml): mantiene la PR
  desde main con el SDK oficial **17.11.2**, fijado por npm lock. Node se utiliza
  únicamente para las herramientas de CI; la aplicación continúa en Python.
- El SDK del gestor utiliza el token temporal de la App para PR y tag/release.
  GITHUB_TOKEN tiene contents/pull-requests read y actions write para el despacho.
- Las comprobaciones tienen permisos de lectura. Solo el job de publicación
  recibe packages write y contents write para añadir evidencias a la release.
  Los checkouts no conservan credenciales Git y no hay git push desde CI.

La implantación anterior creaba las PR con GITHUB_TOKEN y exigía **Approve
workflows to run** antes de fusionar. El usuario elige la App para eliminar
esa aprobación adicional. Un workflow_dispatch sobre la rama no sustituye el
check obligatorio; las PR de la App utilizan su evento pull_request normal.
Tras crear la release, el gestor sí utiliza workflow_dispatch con el tag para
publicar: aquí se trata de un despliegue, no del check obligatorio de una PR.

## Versiones y metadatos

La serie propia parte de **1.0.0**; v1.13.0 es histórica, se excluye y se reserva.
[Configuración](../release-please-config.json) y
[manifest](../.release-please-manifest.json) registran la integración.

| Commits desde la publicación anterior | Incremento |
|---|---|
| `tipo!: ...` o pie `BREAKING CHANGE: ...` | Mayor: 1.2.3 → 2.0.0 |
| `feat: ...` o `fix: ...`, con scope opcional | Menor: 1.2.3 → 1.3.0 |
| Resto: docs, build, test, chore, ops, etc. | Parche: 1.2.3 → 1.2.4 |

El helper Python de solo lectura calcula esta política y la pasa a Release
Please como releaseAs. Después de crear releases pendientes, el gestor solicita su publicación
inmediatamente, actualiza los tags locales y recalcula la siguiente versión.
Así una PR funcional fusionada después de la PR de versión se propone para la
publicación posterior, incluso con varias fusiones cercanas.
Se comprueba que main no avance durante la propuesta. El CI de la PR del bot
calcula además la versión esperada desde su base y rechaza una propuesta que
omita el incremento requerido por esos cambios.
El SDK actualiza pyproject.toml, únicamente la entrada
mealie-enricher de uv.lock, ARG VERSION del Dockerfile, manifest y CHANGELOG.
No cambia las versiones de dependencias. Las anotaciones del Dockerfile y el
selector TOML del lock se prueban con los actualizadores reales del SDK.

Utiliza Conventional Commits en los commits o en el título de PR si se fusiona
con squash. No hay commit de versión directo ni `[skip ci]` en la PR de release.

## Publicación y recuperación

La ejecución manual recibe `release_tag` vacío para solo validar, o `vX.Y.Z`
para publicar una release existente de este flujo. Se rechazan tags inválidos,
la versión histórica, releases borrador/preliminares, commits fuera de main y
cualquier discrepancia entre tag, revisión y los cuatro metadatos de versión.
El validador se obtiene de la revisión de confianza del workflow de main;
consulta los archivos del tag con git show sin ejecutar su código. Comprueba
ancestría y metadatos y exige que exista una PR de versión del bot fusionada
exactamente en ese SHA. Solo entonces hace checkout del SHA fijo y ejecuta la
suite. Resolución y pruebas forman un único job obligatorio: un fallo de
resolución no puede dejar el check obligatorio omitido.

Prefijo: `ghcr.io/brunofelixns/mealie-enricher`.

| Tags | Contenido |
|---|---|
| `X.Y.Z` / `latest` | Base sin datos |
| `X.Y.Z-bedca` / `bedca` / `latest-bedca` | DuckDB y tres CSV originales |

Las publicaciones tienen grupos distintos de los pushes y una cola propia
con queue: max (hasta 100 pendientes). El job de publicación se serializa para
que el control de aliases y la promoción no compitan con otra release.
Se construyen candidatos inmutables y se comprueban ambas arquitecturas antes
de promover versiones. Los manifiestos hijos se ejecutan por su propio digest
para evitar el conflicto del almacén clásico de Docker. ARM se prueba con QEMU.
Los índices conservan el formato sin attestations embebidas de BuildKit.
Antes de promocionar se ejecuta [ci/security.py](../ci/security.py) sobre los
cuatro manifiestos hijos por digest. Se rechazan informes vacíos o incompletos
y vulnerabilidades HIGH/CRITICAL con una versión corregida disponible. Los
hallazgos sin corrección y de menor gravedad permanecen en los informes completos.
El escáner no monta el socket Docker; consulta el registro con su imagen fijada.

Se obtiene un SBOM CycloneDX de cada plataforma a partir del mismo inventario
escaneado. `actions/attest` firma los cuatro SBOM y la procedencia de promoción
de ambos índices, usando OIDC y almacenando las attestations en GitHub y GHCR.
La procedencia es de tipo SLSA v1 con buildType `verified-promotion/v1`: identifica
la revisión exacta de la release, el digest del candidato y la ejecución que lo
verificó y promocionó. Describe también reintentos que reutilizan candidatos;
no atribuye una reconstrucción inexistente ni confunde el SHA de main con el
checkout publicado. No se afirma un nivel de certificación SLSA.

Manifiesto, informes, SBOM y bundles de firma se suben como **assets de la release**
antes de mover aliases. Sus nombres incluyen run ID e intento y no sustituyen
evidencias de intentos previos. No dependen de la retención de Actions. Los
reintentos vuelven a escanear antes de firmar y promocionar; un fallo no deja
un recibo de seguridad correcto reutilizable.

El control de cobertura se conserva desde el checkout de confianza antes de
cambiar al código del tag. Para publicar, las herramientas genéricas de escaneo
y firma se obtienen del SHA del workflow en `.cache/trusted-ci`; la receta de
construcción y el dataset continúan perteneciendo al tag validado. Así una
release anterior no necesita contener los helpers recién incorporados.

Verificación de un digest publicado por este flujo:

```bash
gh attestation verify oci://ghcr.io/brunofelixns/mealie-enricher@sha256:DIGEST \
  --repo brunofelixns/mealie-enricher \
  --predicate-type https://slsa.dev/provenance/v1
```

Los SBOM acreditan manifiestos hijos, no el índice multiplataforma; usar su digest
y el predicate type CycloneDX al verificar su attestation. Las releases históricas
no adquieren firmas retrospectivas por integrar estos workflows.

Los tags de versión nunca se sustituyen por otro digest. Un reintento antiguo
solo repara esos tags y no mueve latest/bedca ni la release vigente de GitHub.
No existe una transacción global entre todos los tags y GitHub: un fallo puede
dejar publicación parcial. Re-run failed jobs recupera la misma publicación;
también se puede lanzar el workflow en main con el tag publicado correspondiente.
Los tags anteriores a esta implantación conservan su pipeline histórico.

El gestor también reconcilia las releases del bot sin el recibo de publicación
GHCR en sus notas. Si falló la petición de workflow_dispatch después de crear
la release, reintentar el gestor recupera esa solicitud aunque el SDK ya no
devuelva la release como nueva. No duplica una publicación que siga en curso.
La creación de PR y esta reconciliación se mantienen separadas.

La release y el tag se crean antes de la construcción; si falla la imagen,
la ejecución queda roja y los aliases conservan el artefacto previo. Las notas
solo reciben los digests verificados cuando acaba la publicación correctamente.

El paquete mantiene Write en Manage Actions access únicamente para este repo.
Para arrancar con datos incluidos, usar
[.env.bedca.example](../docker/.env.bedca.example), manteniendo las
[condiciones propias de BEDCA](../docker/bedca/NOTICE.md).
El dataset se obtiene de un commit fijo, con tres SHA-256 comprobados; cambiar
la exportación requiere actualizar conjuntamente commit, checksums y versión.

## Evidencia histórica: primera publicación y pipeline sustituido


- YAML/expresiones correctos con actionlint 1.7.12 oficial y checksum verificado.
- 28 pruebas Git de versión, metadatos, reintentos, conflictos y push atómico.
- 10 pruebas del informe completo y de la promoción de imágenes.
- Suite ordinaria local: **372 correctas y 24 Docker omitidas en 165,32 s**.
  Actions activa las integraciones; esta revisión contiene 396 escenarios.
- Revisión independiente: corregida la descarga de imágenes necesaria para un
  runner vacío; sin otros hallazgos accionables.

Primera ejecución real:

- [Actions 41434199911](https://github.com/brunofelixns/mealie-enricher/actions/runs/41434199911), revisión `7ec463e0720df68f22824d2ebd2428ef7949b755`.
- Job de validación correcto en 4 min 46 s: **396 pruebas correctas, ninguna
  omitida**, en 196,34 s de pytest. Se comprobaron datos reales y contenedores
  en un runner vacío.
- La publicación calcula 1.0.0 y autentica el token, pero el paquete creado
  anteriormente rechaza el primer push con `permission_denied: write_package`.
  GitHub muestra la lista de Actions access vacía; el permiso de escritura del
  job no sustituye la concesión del propio paquete.
- Se prepara el acceso limitado a este repositorio para reintentar únicamente
  el job fallido. Las etiquetas estables y las referencias de versión no se
  modifican tras ese primer fallo. La publicación no se declara completada.
- El usuario confirma la concesión: se añade únicamente
  `brunofelixns/mealie-enricher` con **Write** en **Manage Actions access**.
  Se reintenta solo la publicación fallida, conservando la validación correcta.
- El reintento publica el candidato base y verifica amd64. La descarga de ARM
  falla con `cannot overwrite digest`: el runner usa Docker 28 con overlay2,
  que no permite asociar ambas plataformas a la misma referencia de índice.
  Se corrige la comprobación para seleccionar los manifiestos hijos de cada
  arquitectura. Tres regresiones fallan antes del cambio y las siete pruebas
  de publicación pasan después. La suite pasa a contener 399 escenarios.
- La corrección verifica el candidato real desde GHCR: ejecuta correctamente
  amd64 y arm64 (QEMU), con versión 1.0.0. Suite local: **375 correctas y 24
  Docker omitidas en 164,53 s**; Ruff, formato, mypy y actionlint correctos.
  Revisión independiente sin hallazgos. Se requirió una nueva ejecución de
  Actions con todas las integraciones antes de publicar esta revisión.
- Nueva [ejecución 41449216230](https://github.com/brunofelixns/mealie-enricher/actions/runs/41449216230),
  revisión `2265d33a5eaf95d5b7a276fc600c85f6011b05a5`: **399 pruebas correctas,
  ninguna omitida**, en 200,39 s. Validación completa correcta en 4 min 49 s.

### Publicación 1.0.0 verificada

La misma ejecución termina correctamente: publicación en 3 min 29 s y
[release v1.0.0](https://github.com/brunofelixns/mealie-enricher/releases/tag/v1.0.0)
publicada. Main y el tag apuntan a `2265d33a5eaf95d5b7a276fc600c85f6011b05a5`;
GitHub identifica 1.0.0 como su release vigente.

| Variante y aliases verificados | Digest del índice |
|---|---|
| `1.0.0`, `latest` | `sha256:68340685ff50074b11db71cc6e26e08a56f4a159b36a496666e6350d4e70a7d6` |
| `1.0.0-bedca`, `bedca`, `latest-bedca` | `sha256:c1bbdc9a2c98c896c06c46128b1ffc58de7c3766f8549b45aa25362144bb9221` |

Consulta independiente de GHCR sin credenciales: los cinco tags son públicos,
sus digests coinciden con la release y cada índice contiene `linux/amd64` y
`linux/arm64`. También se verifican por hash sus cuatro manifiestos hijos.
El workflow ejecuta las cuatro combinaciones de variante/arquitectura con
versión 1.0.0 y usuario 1000; ambas BEDCA contienen 957 alimentos y tres CSV.
ARM se ejecuta mediante QEMU. No se generan SBOM ni attestations de provenance.

La imagen BEDCA ya permite arrancar con los datos incluidos mediante
`ghcr.io/brunofelixns/mealie-enricher:bedca`. La publicación anterior `1.13.0`
se conserva y sus tags de versión no se sobrescriben.


## Implantación de Release Please

Protección aplicada por API: PR obligatoria, Suite completa y calidad del
proveedor GitHub Actions (app 15368), strict/up-to-date y enforce_admins activos;
force push y borrado desactivados, conversaciones resueltas. Revisores mínimos:
0 para permitir al único mantenedor fusionar sus PR después de CI.

Actions conserva permisos generales read; se habilita la opción de GitHub que
permite al token crear PR. Cada job declara sus permisos concretos. No se han
añadido secretos ni credenciales permanentes.

Revisión final: corregidas la resolución desde el tag no confiable, el check
omitido por dependencia, la cola de publicaciones, el recálculo después de crear
releases y el uso incorrecto de workflow_dispatch como check de PR. Regresiones
observadas antes de corregir y verificadas después. La validación del lock real
con el SDK confirma que solo cambia la versión del paquete propio.

Actionlint 1.7.12 no reconoce todavía queue: max, documentado por GitHub. Se
excluye exclusivamente ese diagnóstico al ejecutar el linter; la aceptación
de la propiedad se verificará también en GitHub Actions al abrir la PR.
El resultado de integración y la PR del bot se registrarán después.

La revisión automática de la PR de implantación detectó cuatro casos adicionales:
concurrencia compartida entre push y PR, nombre de rama por defecto de un paquete,
recuperación tras fallo del despacho y avance de main durante la propuesta.
Se separan los grupos por evento, se configura separate-pull-requests=false y se
añaden regresiones con PR construida por el SDK real, recuperación y comprobación
de la versión propuesta contra la base. Las 14 pruebas Node son correctas.

La implantación #1 se integra con dbdab01 tras 396 pruebas Python y 14 Node en
verde. El gestor crea realmente la PR #2 para 1.0.1 y su diff contiene solo
los cuatro metadatos y CHANGELOG. Su ejecución de PR requiere aprobación con
GITHUB_TOKEN; el mantenedor la aprueba tras revisar el diff.

La primera validación de 1.0.1 descubre una fixture del SDK fijada a 1.0.0;
se corrige para seguir la versión del manifest. Se fija además minimatch 11.0.4
solo para el consumidor de CI git-file-utils, por el aviso
[GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249).
La selección de archivos mediante la API real del consumidor se comprueba con
esta versión. No cambia ninguna dependencia de la aplicación Python.

### Cierre remoto de la implantación

- [PR de implantación #1](https://github.com/brunofelixns/mealie-enricher/pull/1)
  y [corrección #3](https://github.com/brunofelixns/mealie-enricher/pull/3)
  fusionadas únicamente después de su CI correcto. Main vigente:
  `d104e9fd969c61447dc548539afa7f179d1ab645`.
- El gestor [41460730777](https://github.com/brunofelixns/mealie-enricher/actions/runs/41460730777)
  actualiza automáticamente la misma [PR #2, versión 1.0.1](https://github.com/brunofelixns/mealie-enricher/pull/2).
  Su diff incluye solo los cuatro metadatos y CHANGELOG; conserva dependencias.
- Su [CI 41460796759](https://github.com/brunofelixns/mealie-enricher/actions/runs/41460796759)
  termina con **396 Python correctas, ninguna omitida, y 15 Node correctas**.
  Pytest tarda 218,56 s. Head probado:
  `ee4e6b0c52bdd9aff5733b2b0ee594e4fe19e4e2`; PR OPEN y CLEAN.
- Protección comprobada de nuevo por API: PR y check obligatorio app15368,
  strict y enforce_admins activos; force push y borrado desactivados.
- Ambos pushes de implantación a main ejecutan CI correctamente sin publicar.
  La PR 1.0.1 se deja abierta: su fusión decidirá la publicación siguiente.
- El mantenedor aprobó el CI real de la PR del bot después de revisar su diff.
  Con GITHUB_TOKEN este paso será necesario en las siguientes actualizaciones;
  una GitHub App permitiría CI sin esa aprobación adicional. No se configura
  ninguna credencial nueva al no haberse elegido esa alternativa.
- GitHub confirma Dependabot #1 en estado **fixed** tras la corrección de CI.

## Ampliación elegida: App dedicada

Tras el cierre anterior el usuario elige GitHub App para CI totalmente
automático y confirma su creación, instalación limitada y secreto de Actions.
La App está registrada e instalada con los permisos descritos arriba.
El canje del manifest se realiza por HTTPS dentro del proceso local; la clave
se envía por stdin al secreto del repositorio, con destino github.com explícito.
No se imprime ni se guarda en archivos. El callback local se cierra al terminar.

La [PR #4](https://github.com/brunofelixns/mealie-enricher/pull/4), commit
e5f13e74084d6c3bb0d17acdd626a516ff73815a, pasa el
[CI 41470064040](https://github.com/brunofelixns/mealie-enricher/actions/runs/41470064040):
396 Python sin omisiones en 194,08 s y 20 Node correctas. La publicación se omite.
La revisión independiente no deja hallazgos pendientes. Tras configurar el
secreto y las dos variables, la PR se integra mediante squash
`4161077379282d790eb337c18445e0145dd57676`.

El [gestor 41471806436](https://github.com/brunofelixns/mealie-enricher/actions/runs/41471806436)
termina correctamente: crea el token limitado, comprueba el slug y actualiza la
misma PR #2 con autor de commit `mealie-release-brunofelixns[bot]`. Revoca el token
al finalizar. El [CI pull_request 41471871230](https://github.com/brunofelixns/mealie-enricher/actions/runs/41471871230)
arranca automáticamente para `7b37d78efb1fc6ea73db0db36e75349c92ef5c1a`, sin
aprobar workflows ni usar un despacho manual como sustituto del check.
La PR 1.0.1 permanece abierta; no se publica una release durante esta activación.

## Referencias

- [Release Please](https://github.com/googleapis/release-please).
- [Eventos generados por GITHUB_TOKEN](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
- [Protección de ramas](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

- [Checks obligatorios y eventos elegibles](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).
- [Cola de concurrencia](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
