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

El paquete debe conceder acceso al repositorio en **Manage Actions access**.
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

La ejecución real y sus digests se registrarán después de activar el workflow.

## Referencias

- [Imágenes y GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images).
- [Concurrencia](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
