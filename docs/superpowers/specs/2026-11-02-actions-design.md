# Pruebas y publicación automática con GitHub Actions

## Solicitud

Cada subida debe ejecutar toda la suite y, si pasa en main, actualizar GHCR con
versión automática. Se parte de la versión propia 1.0.0 y se incluyen tanto la
imagen base como BEDCA con sus CSV, según el alcance no comercial ya confirmado.

## Decisiones técnicas

- Un workflow para push, pull_request y ejecución manual. Las ramas y PR solo
  validan. La publicación se limita al main del repositorio propietario.
- Python/uv bloqueados, Ruff, formato, mypy y suite completa con las 24 pruebas
  Docker existentes habilitadas, Mealie real aislado y BEDCA real.
- La exportación BEDCA se obtiene de un commit fijo y se verifican los SHA-256
  de los tres CSV antes de construir. No se añaden CSV ni claves al repositorio.
- La primera publicación propia es 1.0.0; v1.13.0 se excluye por ser numeración
  histórica. Después: cambio incompatible -> major; feat/fix -> minor; resto
  -> patch. Se respetan las convenciones de commits del proyecto.
- Un helper Python de biblioteca estándar prepara los metadatos y un commit/tag
  de versión local reproducible. Se evita introducir Node o un servicio de PR
  de release que requiera una aprobación manual para cada publicación.
- La suite valida el código. Tras calcular la versión, la construcción y los
  smoke tests verifican que los metadatos nuevos coinciden con los contenedores.
- Se publican candidatos por SHA y, tras construir y comprobar ambas imágenes,
  se empujan commit/tag de versión de forma atómica y se promocionan los tags.
  El último tag estable no se actualiza tras fallos de pruebas o construcción.
- Los reintentos reutilizan versión, commit y candidatos; una ejecución antigua
  no puede sustituir una publicación posterior. Git nunca utiliza force push.
- Se conservan base latest/version y BEDCA bedca/version-bedca, para amd64/arm64.
  La publicación usa GITHUB_TOKEN con permisos mínimos por job, sin PAT nuevo.

## Verificación y límites

Pruebas con repositorios Git temporales para versiones, reintentos y concurrencia;
validación real del YAML con actionlint; suite local y ejecución en Actions.
Se comprobarán registros y digests antes de declarar publicada una versión.
Un fallo de permisos o de cuota externo debe quedar identificado, sin presentarlo
como un fallo de código ni como una publicación satisfactoria.
