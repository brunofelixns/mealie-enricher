# GitHub App para CI automático

El usuario elige GitHub App para eliminar la aprobación de los workflows de PR
del bot. Se conserva main protegida y la decisión de publicar al fusionar la PR.

## Diseño

- App privada, instalada solo en brunofelixns/mealie-enricher: Contents,
  Pull requests e Issues write; Metadata read implícito. Sin webhooks, permisos
  de cuenta/organización, administración, workflows ni acceso a paquetes.
- Clave privada únicamente en RELEASE_APP_PRIVATE_KEY de Actions.
  Client ID y slug en variables RELEASE_APP_CLIENT_ID/RELEASE_APP_SLUG.
  No se guarda en Git ni .env. El Client ID es público, no la clave privada.
- Acción oficial create-github-app-token v3 fijada por SHA; token limitado a
  ese repositorio y a esos tres permisos, revocado al finalizar el job.
- SDK de Release Please utiliza la App. GITHUB_TOKEN se conserva con lectura
  y Actions write para lanzar la publicación; GHCR sigue con el token del job.
- La procedencia admite la App configurada y github-actions[bot], para conservar
  la PR existente creada por el token anterior y los reintentos históricos.
  Se rechazan otros bots, autores humanos y PR ajenas al flujo.
- Sin fallback silencioso: si faltan las credenciales de App, el gestor falla.
- Registrar/instalar la App y guardar su clave requiere la confirmación concreta
  que exige el control del navegador. Preparar código, pruebas y PR antes.

## Pasos

- [x] Pruebas de procedencia con App, transición de autor y rechazo de otro bot/fork.
- [x] Workflow con token temporal, permisos mínimos y comprobación de identidad.
- [x] Documentar, revisar y abrir PR; CI completo obligatorio.
- [x] Preparar registro privado y permisos exactos; confirmar acceso en navegador.
- [x] Instalar solo este repo, almacenar secreto sin mostrarlo y variables.
- [x] Integrar PR tras CI; verificar que el bot actualiza PR y CI arranca sin aprobación.
- [x] Desactivar creación/aprobación de PR mediante GITHUB_TOKEN y registrar evidencia.

La PR de versión 1.0.1 permanece abierta; no se fusiona para publicar una imagen.

## Evidencia de preparación

- PR #4: codex/release-github-app, commit e5f13e74084d6c3bb0d17acdd626a516ff73815a.
- CI pull_request 41470064040, job 125360973514: 396 Python sin omisiones
  en 194,08 s y 20 Node correctas. Publicación omitida por ser PR.
- Revisión independiente de las correcciones sin hallazgos pendientes.
- Confirmación concreta recibida. App privada mealie-release-brunofelixns creada
  e instalada solo en el repositorio. Clave en secreto, Client ID/slug en variables;
  sin clave en disco ni logs. Callback local detenido después del registro.
- PR #4 integrada en 4161077379282d790eb337c18445e0145dd57676.
- Gestor 41471806436 correcto: token limitado, identidad comprobada, misma PR #2
  actualizada y token revocado. CI pull_request 41471871230 arranca sin aprobación
  manual sobre 7b37d78efb1fc6ea73db0db36e75349c92ef5c1a.
- Actions por defecto read; can_approve_pull_request_reviews=false verificado.
