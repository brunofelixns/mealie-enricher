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

## Workflows y permisos

- [ci-release.yml](../.github/workflows/ci-release.yml): pushes, PR y ejecución
  manual. Resuelve la revisión, valida metadatos, ejecuta los tests del SDK,
  Ruff, formato, mypy y toda la suite Python/Docker sin omisiones.
- [release-please.yml](../.github/workflows/release-please.yml): mantiene la PR
  desde main con el SDK oficial **17.11.2**, fijado por npm lock. Node se utiliza
  únicamente para las herramientas de CI; la aplicación continúa en Python.
- El gestor recibe contents/pull-requests/issues/actions write. Utiliza
  GITHUB_TOKEN para su PR, tag/release y workflow_dispatch; no añade PAT ni claves.
- Las comprobaciones tienen permisos de lectura. Solo el job de publicación
  recibe packages write y contents write para añadir evidencias a la release.
  Los checkouts no conservan credenciales Git y no hay git push desde CI.

GitHub crea la ejecución pull_request del bot en estado de aprobación cuando
la PR se crea con GITHUB_TOKEN. El mantenedor debe usar **Approve workflows to
run** antes de fusionar. Un workflow_dispatch sobre la rama no sustituye el check
obligatorio, por lo que no se utiliza para validar PR. Para eliminar esta
aprobación adicional hace falta una GitHub App o PAT con permisos limitados;
la elección se ha consultado al usuario y no se crea ninguna credencial sin ella.
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
No se generan SBOM ni attestations de provenance.

Los tags de versión nunca se sustituyen por otro digest. Un reintento antiguo
solo repara esos tags y no mueve latest/bedca ni la release vigente de GitHub.
No existe una transacción global entre todos los tags y GitHub: un fallo puede
dejar publicación parcial. Re-run failed jobs recupera la misma publicación;
también se puede lanzar el workflow en main con el tag publicado correspondiente.
Los tags anteriores a esta implantación conservan su pipeline histórico.

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

## Referencias

- [Release Please](https://github.com/googleapis/release-please).
- [Eventos generados por GITHUB_TOKEN](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
- [Protección de ramas](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

- [Checks obligatorios y eventos elegibles](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).
- [Cola de concurrencia](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
