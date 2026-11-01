# Publicación del código en GitHub

Este documento registra la primera subida privada del 2026-10-29. La [publicación open source del 2026-11-01](14-publicacion-open-source.md) actualiza la visibilidad e incorpora la imagen pública de GHCR.

## Destino autorizado

El usuario solicita publicar el código en [brunofelixns/mealie-enricher](https://github.com/brunofelixns/mealie-enricher) y preparar un README visual con una imagen representativa y el logo de Mealie.

El repositorio remoto se comprobó vacío y privado antes de la primera subida. La publicación del código conserva su visibilidad; no solicita publicar una imagen Docker ni cambiar la visibilidad del repositorio.

Esta solicitud autoriza inicializar Git en el directorio del proyecto, crear la rama main y conectar el remoto indicado. Sustituye la decisión anterior de no inicializar Git durante la migración.

## Contenido preparado

- Aplicación Python, dependencias bloqueadas, migraciones, pruebas y capturas sintéticas.
- Dockerfile, Compose de desarrollo y carpeta docker de despliegue.
- Documentación de alcance, migración, operación y etiquetas.
- README con cabecera, logo oficial, portada ilustrada, navegación, inicio rápido y guías.
- Atribución del logo oficial y copia de su licencia; prompt y origen de la imagen generada.

Los recursos visuales se encuentran en [assets](assets/README.md). La portada se generó con la herramienta integrada y usa el logo oficial como referencia.

## Comprobaciones antes de subir

- Verificar los enlaces locales del README y la documentación.
- Ejecutar las comprobaciones locales de formato, tipos y pruebas de la aplicación.
- Examinar el índice Git para excluir entornos, cachés, archivos .env reales y datos locales.
- Comprobar que las claves de los fixtures son sintéticas.
- Subir mediante Git y comparar el commit remoto con el local.

La publicación de la imagen de GHCR y una ejecución remota de CI siguen siendo verificaciones distintas de la subida del código.

## Verificación local de la versión preparada

- 189 pruebas Python aprobadas y 2 Docker opt-in omitidas; la ejecución ordinaria tardó 11.22 s.
- Ruff correcto y 73 archivos con formato correcto; mypy sin incidencias en 36 archivos.
- 237 archivos preparados, aproximadamente 3.3 MB, incluidos los recursos visuales.
- Comprobación de rutas de exclusión y patrones de credenciales: sin hallazgos.
- Enlaces y recursos locales de 16 documentos Markdown comprobados.
- README renderizado por la API GFM de GitHub: 5 tablas y 7 imágenes, incluidos la portada y el logo.
- NOTICE se conserva de la referencia sin reformatear; sus espacios finales y salto final adicionales son heredados. Los archivos propios pasan la comprobación de whitespace.

## Publicación verificada

- Código subido a main en el commit e7e737507553be41913704167c04fb10407fe4dd.
- La referencia remota se comparó con HEAD local y coincidía.
- README, app.py, Compose de despliegue, logo oficial y portada comprobados contra sus hashes remotos.
- GitHub reconoce main como rama predeterminada y conserva la visibilidad privada del repositorio.
- Este registro se añade después de la subida del código para documentar el resultado observado.
- No se ha publicado una imagen Docker en GHCR.
