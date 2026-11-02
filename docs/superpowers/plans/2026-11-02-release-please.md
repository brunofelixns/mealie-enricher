# Release Please Implementation Plan

> **For agentic workers:** Implementación en esta sesión con executing-plans y revisión independiente final. El usuario ya ha elegido el diseño y ha solicitado aplicarlo.

**Goal:** Exigir PR y CI en main; publicar GHCR únicamente tras fusionar la PR de versión.

**Architecture:** CI de lectura con resolución explícita de la revisión; gestor Release Please separado que abre/actualiza su PR y lanza workflows; publicación dependiente de toda la suite y del tag validado.

**Tech Stack:** GitHub Actions, Release Please SDK 17.11.2 (solo CI), Python, uv, Buildx, GHCR.

**Spec:** [Diseño aprobado por la solicitud](../specs/2026-11-02-release-please-design.md).

## Global Constraints

- No cambios de aplicación ni dependencias Python.
- Primera versión existente 1.0.0; excluir y reservar la histórica 1.13.0.
- Breaking mayor; feat/fix menor; resto parche.
- GITHUB_TOKEN, sin credenciales nuevas y sin escrituras directas a main.
- Toda la suite Docker, Mealie aislado y BEDCA real antes de publicar.
- No fusionar automáticamente la PR de versión.

## Review Focus

- Un workflow manual no puede publicar un tag falso o metadatos distintos.
- El bot debe recibir CI aunque sus eventos no arranquen workflows normales.
- Un reintento de una release anterior no retrocede latest/bedca.
- La protección no puede permitir saltarse PR/checks al administrador o bot.
- Actualizar uv.lock debe conservar las versiones de dependencias.

## Tasks

- [x] Sustituir el helper de commits/push por política y validación de metadatos de solo lectura. Probar mayor/menor/parche, legado, tags y cambios inconsistentes antes de implementar.
- [x] Integrar SDK oficial fijado, manifest/config y actualizadores de versiones. Probar los actualizadores reales sin red y el lanzamiento explícito de publicaciones.
- [x] Refactorizar workflows: resolver tag publicado desde código confiable, suite exacta, publicación sin Git push, cola de publicaciones y promoción sin rollback. Probar los casos de revisión y validar con actionlint.
- [x] Actualizar docs/D16, ejecutar controles y suite; revisión independiente y correcciones necesarias.
- [x] Crear PR de implantación, exigir CI en main y activar permisos mínimos. Fusionar solo tras pruebas correctas; comprobar gestor y PR de versión reales.
- [x] Registrar evidencia de protección y de la PR abierta. La publicación siguiente depende de que el usuario fusione esa PR.

## Cierre remoto

- PR #1 integrada en dbdab01 con 396 pruebas Python sin omisiones y 14 del SDK.
- PR #3 integrada en d104e9f con 396 Python sin omisiones y 15 del SDK; corrige la fixture para incrementos reales y la dependencia de CI señalada por Dependabot. El aviso #1 consta como fixed.
- Gestor 41460730777 correcto: actualiza la misma PR #2, versión 1.0.1, con los dos cambios ya fusionados en main.
- PR #2: head ee4e6b0c52bdd9aff5733b2b0ee594e4fe19e4e2; base d104e9fd969c61447dc548539afa7f179d1ab645. Cinco archivos: manifest, CHANGELOG, Dockerfile, pyproject y uv.lock.
- CI de PR #2 aprobado tras revisar el diff: Actions 41460796759, 396 Python correctas sin omisiones en 218,56 s y 15 Node correctas. Estado CLEAN y OPEN; no se fusiona.
- Protección verificada: PR requerida, strict/up-to-date, check Suite completa y calidad de Actions app15368 y enforce_admins; sin force push ni borrado.
- Con GITHUB_TOKEN las ejecuciones de PR del bot requieren aprobación del mantenedor. No se crean credenciales nuevas; la alternativa de GitHub App queda disponible si el usuario quiere eliminar ese paso.
- La publicación 1.0.1 no se ejecuta hasta fusionar la PR de versión. Los pushes funcionales a main ejecutaron CI sin publicar.
