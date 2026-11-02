# Main protegida y PR de publicación

El usuario aprueba sustituir la publicación automática por push por protección
de main y Release Please. El código entra mediante PR con pruebas correctas;
una PR independiente reúne versión y changelog. Fusionarla decide publicar.

## Diseño elegido

- Main exige PR, la comprobación `Suite completa y calidad` y rama actualizada.
  Se aplica también a administradores; no se exigen revisores externos en este
  repositorio personal. No se permiten force push ni borrado de main.
- Release Please mantiene su PR mediante el SDK oficial 17.11.2, utilizado solo
  en CI. Se fija la dependencia con npm lock; Python sigue siendo el runtime.
- Se conserva la política propia: breaking mayor; feat/fix menor; resto parche.
  Un helper Python de solo lectura calcula la propuesta y la pasa a Release
  Please como `releaseAs`. Se reserva 1.13.0 y se parte de 1.0.0/2265d33.
- Release Please actualiza pyproject, uv.lock, Dockerfile, manifest y changelog.
  No existe un commit de versión directo sobre main ni auto-merge de su PR.
- Se utiliza GITHUB_TOKEN. Sus PR requieren aprobar el workflow de PR;
  workflow_dispatch no satisface el check de PR y solo se usa para publicar
  releases. La alternativa de GitHub App para CI sin aprobación adicional se
  consulta al usuario; no se crean credenciales sin su elección.
- La publicación recibe un tag explícito, valida su release pública y la
  correspondencia tag/commit/metadatos/ancestría main, y ejecuta toda la suite
  sobre ese commit antes de construir/publicar ambas variantes.
- Se conservan candidatos y versiones inmutables, controles de arquitectura y
  BEDCA. Un reintento de una versión antigua no mueve aliases de la vigente.

## Alternativas

El bot anterior escribía main y publicaba cada push: se sustituye por solicitud
expresa. Una GitHub App evitaría el lanzamiento explícito de workflows, pero
añadiría credenciales permanentes y administración. Se elige el token temporal
con workflow_dispatch, una excepción documentada por GitHub para desplegar releases. El check de PR usa el evento pull_request real.

## Alcance y comprobación

No cambian la aplicación, datos, contratos Mealie ni dependencias Python.
Se probarán cálculo y metadatos, rechazo de tags y releases incorrectos,
promoción antigua sin rollback, actualizaciones reales de Release Please,
YAML y suite completa. La activación se integra mediante PR; se verifica la
protección por API y que la PR del bot recibe sus comprobaciones. Esa PR queda
abierta para que el mantenedor decida cuándo publicar.

## Ajustes tras revisión

Resolución de tag desde código de main antes de ejecutar el árbol publicado;
procedencia de PR bot fusionada exigida; verificación en un solo job obligatorio;
publicaciones en cola propia max y promoción serial; recálculo de la siguiente
versión después de crear releases y despacho antes de mantener la PR siguiente.
