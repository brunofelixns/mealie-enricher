# Publicación open source

Fecha: 2026-11-01.

## Resultado

- [Repositorio público](https://github.com/brunofelixns/mealie-enricher), con `main` como rama predeterminada y licencia GPLv3 conservada.
- [README principal en inglés](../README.md), [presentación en español](README.es.md), índice técnico español y guías de despliegue en ambos idiomas.
- Descripción GitHub: “Self-hosted nutrition estimates and automatic tags for Mealie recipes, with Open Food Facts and optional DuckDB/BEDCA catalogs.”
- Temas: `mealie`, `nutrition`, `recipes`, `self-hosted`, `python`, `fastapi`, `docker`, `duckdb`, `bedca`, `open-food-facts`.
- [Paquete GHCR público](https://github.com/brunofelixns/mealie-enricher/pkgs/container/mealie-enricher), conectado al repositorio, descargable sin credenciales.
- Guía de contribución, créditos upstream, licencia y avisos de terceros conservados. Los CSV BEDCA y los datos locales no se redistribuyen.

## Imagen publicada

~~~text
ghcr.io/brunofelixns/mealie-enricher:1.13.0
ghcr.io/brunofelixns/mealie-enricher:latest
~~~

Ambos tags apuntan al índice multiplataforma:

~~~text
sha256:296af6395411957581f8157b3dfd7844cffd62a62313c504e61e3e82b371f158
~~~

Referencia fija para desplegar exactamente esta imagen:

~~~text
ghcr.io/brunofelixns/mealie-enricher@sha256:296af6395411957581f8157b3dfd7844cffd62a62313c504e61e3e82b371f158
~~~

| Plataforma | Manifiesto publicado |
|---|---|
| linux/amd64 | `sha256:b84d6c84749c25c7d299412f7617297517d19549d4130552d3cc293f2f63b9b9` |
| linux/arm64 | `sha256:3b6cdba3ed470d6b49dc2c6caf6c39db9c8ee54e19c6ad82111cc659b29f908d` |

La revisión de código identificada por la etiqueta OCI es `628e0f4a19ce1ef7181b4fd6657782e526969007`. Los commits posteriores que registran esta evidencia solo actualizan documentación. Las etiquetas OCI incluyen proyecto, descripción, URL, repositorio, licencia, versión y revisión. El proceso del contenedor utiliza `appuser`.

## Evidencia ejecutada

- Ruff y comprobación de formato correctos: 98 archivos ya formateados.
- Mypy correcto: 45 archivos fuente.
- Suite ordinaria: **334 aprobadas, 17 omitidas**, en 22.74 s. Las omitidas son integraciones opcionales.
- Seis documentos de presentación/despliegue comprobados sin destinos locales ausentes; portada, navegación de idiomas y diagrama revisados en el README real de GitHub.
- Compose de desarrollo y de despliegue comprobados con configuración de ejemplo; no se utilizaron credenciales de producción.
- Revisión de firmas de credenciales en 299 blobs del historial: sin coincidencias en los patrones comprobados. Los candidatos por nombre fueron los dos `.env.example` y la base de caché sintética de compatibilidad. Esta comprobación es una revisión de publicación, no una auditoría exhaustiva de seguridad.
- Código y archivos de instalación descargados mediante HTTP público sin autenticación.
- Imagen amd64 ejecutada en el host amd64; imagen arm64 ejecutada mediante **QEMU**, con más tiempo de arranque para la emulación. En ambas: `/health`, `/estimator/history` y `/estimator/history.json` correctos; versión 1.13.0, DuckDB y usuario sin privilegios comprobados.
- Los manifiestos publicados conservan exactamente los mismos digests de configuración de las dos imágenes probadas. Se comprobaron anónimamente los dos tags, los manifiestos de cada plataforma, la revisión y el usuario del contenedor.
- `docker pull --platform linux/amd64` aprobado con un directorio de configuración Docker nuevo, sin credenciales.
- Despliegue desde la imagen pública con catálogo sintético: **1 prueba Docker aprobada**, en 21.59 s. Verifica importación, consulta del catálogo, montaje de catálogo en solo lectura y caché en volumen independiente; elimina únicamente su proyecto y volúmenes de prueba.

## Publicación y límites

La publicación se realizó localmente con Docker Buildx. La subida inicial con atestaciones opcionales fue rechazada por el registro. Se publicaron los manifiestos estándar y se verificó el comando reproducible de la [guía de despliegue](../docker/README.md) con `--provenance=false --sbom=false`.

No fue necesario conceder acceso adicional a GitHub Actions ni crear un token personal nuevo. No se configura un workflow de publicación automática.

Esta evidencia no acredita ejecución en hardware ARM nativo, CI remoto ni éxito de los proveedores de IA reales. Las estimaciones y limitaciones funcionales continúan documentadas en el README y en las guías de validación.
