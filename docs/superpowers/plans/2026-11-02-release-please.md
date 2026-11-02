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
- [ ] Crear PR de implantación, exigir CI en main y activar permisos mínimos. Fusionar solo tras pruebas correctas; comprobar gestor y PR de versión reales.
- [ ] Registrar evidencia de protección y de la PR abierta. La publicación siguiente depende de que el usuario fusione esa PR.
