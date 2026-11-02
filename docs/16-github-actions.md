# GitHub Actions: pruebas, versión automática y GHCR

## Flujo

El [workflow](../.github/workflows/ci-release.yml) se ejecuta en pushes, pull
requests y manualmente. Instala Python 3.14.6, uv 0.11.28 y dependencias bloqueadas;
comprueba Ruff, formato y mypy. Obtiene BEDCA desde un commit fijo y verifica los
SHA-256 de los tres CSV antes de construir las imágenes.

Descarga Mealie y el servidor OFF de prueba para un runner vacío. Ejecuta toda
la suite, incluidas Docker, Mealie real aislado, CSV reales y la imagen BEDCA.
El informe JUnit debe tener cero fallos y cero omisiones para poder publicar.
No se utilizan OpenAI ni la instalación personal de Mealie.

Solo en main del repositorio propietario, un segundo job prepara la versión,
construye candidatos base/BEDCA para amd64 y arm64 y verifica versión, revisión,
usuario y catálogo. ARM se comprueba mediante QEMU. Después guarda commit/tag
de versión atómicamente, promociona las imágenes y crea la release en GitHub.
La comprobación ejecuta el manifiesto específico de cada arquitectura, evitando
asociar dos imágenes distintas al mismo digest de índice en Docker clásico.

Los PR tienen permisos de lectura. Únicamente la publicación recibe
`contents: write` y `packages: write`, usando `GITHUB_TOKEN`, sin un PAT nuevo.
Las acciones están fijadas por SHA. Los informes y manifiestos se conservan
como artefactos de cada ejecución.

## Versiones

La primera versión propia es **1.0.0**. Se excluye el tag histórico `v1.13.0` y
se reserva su número para no sobrescribir aquel artefacto.

| Commits desde la publicación anterior | Incremento |
|---|---|
| `tipo!: ...` o pie `BREAKING CHANGE: ...` | Mayor: 1.2.3 → 2.0.0 |
| `feat: ...` o `fix: ...`, con scope opcional | Menor: 1.2.3 → 1.3.0 |
| Resto: `docs`, `build`, `test`, `chore`, etc. | Parche: 1.2.3 → 1.2.4 |

Se aplica el incremento más alto. El tratamiento de `fix` sigue la convención
API/UI del proyecto. No hay que editar versiones manualmente: el bot modifica
únicamente `pyproject.toml`, la entrada del proyecto en `uv.lock` y `ARG VERSION`
del Dockerfile. No actualiza dependencias. El commit de versión usa `[skip ci]`
para evitar bucles; el tag es `vX.Y.Z`.

Versión, commit y tag son reproducibles. Reintentar el mismo workflow no vuelve
a incrementar; una ejecución antigua no sustituye la publicación posterior.
Una carrera de pushes se resuelve sin force push y sin promocionar código viejo.

## Imágenes

Prefijo: `ghcr.io/brunofelixns/mealie-enricher`.

| Tag | Contenido |
|---|---|
| `X.Y.Z` / `latest` | Imagen base sin datos |
| `X.Y.Z-bedca` / `bedca` / `latest-bedca` | DuckDB y CSV originales incluidos |

Usa [.env.bedca.example](../docker/.env.bedca.example) para arrancar con los
datos incluidos. Se mantienen las [condiciones BEDCA](../docker/bedca/NOTICE.md),
separadas de la licencia del código, y el alcance no comercial confirmado.

Los candidatos `build-<revision>` y `build-<revision>-bedca` se verifican antes
de los tags estables. Un tag de versión nunca se reemplaza por otro digest.
No existe una transacción global para GitHub y todos los tags GHCR: una caída
de red puede dejar promoción parcial. El reintento reutiliza los candidatos y
completa la operación. `latest` se mueve únicamente después de preparar y
verificar ambas variantes y de guardar las referencias Git.

## Operación

El paquete debe conceder acceso **Write** al repositorio en **Manage Actions access**.
Si se cambia la protección de main, también debe permitirse el commit de versión
del bot. El flujo falla sin saltarse reglas ni utilizar force push.

Para recuperar un fallo transitorio usa **Re-run failed jobs**. También puedes
ejecutar manualmente el workflow en main: una release ya publicada no vuelve a
publicarse ni incrementa otra vez la versión.

Para actualizar BEDCA se cambian conjuntamente el commit fijado en la acción
compuesta, `ci/bedca.sha256` y la versión de datos de las construcciones. Los
datos no entran en Git; se descargan verificados durante CI y quedan en la variante.

## Verificación de esta entrega

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
  Revisión independiente sin hallazgos. Se requiere una nueva ejecución de
  Actions con todas las integraciones antes de publicar esta revisión.

## Protección de main y PR de versión

Se ha explicado la alternativa de proteger main y usar Release Please para
mantener una PR con la versión y el changelog. Los cambios de código entrarían
mediante sus propias PR; fusionar la PR de versión decidiría la publicación.
Ese cambio de modelo y la protección de main siguen pendientes. El workflow
descrito aquí todavía publica automáticamente desde main y escribe la versión
directamente mediante el bot.

## Referencias

- [Imágenes y GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images).
- [Concurrencia](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
- [Índices, manifiestos y almacenes multiplataforma](https://docs.docker.com/build/building/multi-platform/).
