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
- [ ] Documentar, revisar y abrir PR; CI completo obligatorio.
- [ ] Preparar registro privado y permisos exactos; confirmar acceso en navegador.
- [ ] Instalar solo este repo, almacenar secreto sin mostrarlo y variables.
- [ ] Integrar PR tras CI; verificar que el bot actualiza PR y CI arranca sin aprobación.
- [ ] Desactivar creación/aprobación de PR mediante GITHUB_TOKEN y registrar evidencia.

La PR de versión 1.0.1 permanece abierta; no se fusiona para publicar una imagen.
