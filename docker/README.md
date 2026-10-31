# Ejecutar la imagen publicada en GitHub

Esta carpeta permite descargar y ejecutar Mealie Enricher desde **GitHub Container Registry (GHCR)**. Solo necesitas Docker con Compose y estos tres archivos; la instalación no requiere Python, uv ni el código fuente del proyecto.

La publicación de la imagen es un paso previo. El nombre del paquete del ejemplo es un marcador: sustitúyelo por la imagen y el tag que realmente hayas publicado.

## 1. Preparar la configuración

Copia docker-compose.yml y .env.example a una carpeta del servidor. Este README puede acompañarlos. Ejecuta los comandos desde esa carpeta.

En Linux/macOS:

~~~sh
cp .env.example .env
~~~

En PowerShell:

~~~powershell
Copy-Item .env.example .env
~~~

Edita al menos:

~~~dotenv
MEALIE_ENRICHER_IMAGE=ghcr.io/tu-usuario-o-organizacion/mealie-enricher:latest
MEALIE_URL=https://tu-mealie.example.com
MEALIE_API_TOKEN=tu-token-de-mealie
~~~

Puedes utilizar exclusivamente tokens por hogar, siguiendo los comentarios de .env.example. Compose carga todas esas variables mediante env_file, sin necesidad de enumerar cada hogar en el YAML.

PUBLISHED_PORT es el puerto del servidor; PORT es el puerto dentro del contenedor. Por ejemplo, PUBLISHED_PORT=8002 y PORT=8000 publican el servicio en el puerto 8002.

MEALIE_URL debe ser accesible desde el contenedor: localhost apuntaría al propio contenedor. Usa la URL de tu servidor Mealie. Si ambos servicios se conectan por nombre de contenedor, deben compartir una red Docker.

El fallback LLM queda deshabilitado inicialmente. Para activarlo, configura LLM_ENABLED=true, LLM_API_KEY y la URL/modelo de tu proveedor. Se conservan las mismas variables de la aplicación.

## 2. Descargar y arrancar

~~~sh
docker compose config --quiet
docker compose pull
docker compose up -d --no-build --wait --wait-timeout 90
docker compose ps
~~~

El Compose usa únicamente image y descarga el paquete indicado en MEALIE_ENRICHER_IMAGE. No contiene build ni necesita un Dockerfile en el servidor.

Con PUBLISHED_PORT=8000:

- Estado: http://localhost:8000/health
- Historial: http://localhost:8000/estimator/history
- Webhook para configurar en Mealie: http://DIRECCION-DEL-SERVICIO:8000/webhook

El historial muestra recetas, estados, cambios, duración, nutrientes y errores, con actualización cada dos segundos y filtros por origen/estado. Las etiquetas automáticas que se guardan en Mealie están en español.

La dirección del webhook debe ser alcanzable desde Mealie. Si cambias PUBLISHED_PORT, utiliza ese puerto en las direcciones externas.

Para consultar registros:

~~~sh
docker compose logs -f --tail 100 calorie-estimator
~~~

## Si la imagen es privada

Las imágenes públicas de GHCR pueden descargarse sin iniciar sesión. Para una imagen privada, inicia sesión antes de docker compose pull:

~~~sh
docker login ghcr.io -u TU_USUARIO_GITHUB
~~~

Cuando Docker solicite la contraseña, introduce un token personal clásico de GitHub con read:packages y acceso al paquete. Ese token sirve para el registro; MEALIE_API_TOKEN sirve para Mealie. [Documentación de GHCR](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Actualizar la versión

Cambia MEALIE_ENRICHER_IMAGE al nuevo tag publicado, o conserva latest si esa es tu política de publicación:

~~~sh
docker compose pull
docker compose up -d --no-build --wait --wait-timeout 90
~~~

Para fijar exactamente una publicación, utiliza un tag de versión existente o su digest:

~~~dotenv
MEALIE_ENRICHER_IMAGE=ghcr.io/tu-usuario-o-organizacion/mealie-enricher@sha256:DIGEST_PUBLICADO
~~~

El tag o digest debe existir y corresponder a una imagen compatible con la arquitectura del servidor.

## Datos y parada

El volumen estimator-cache conserva /app/data/cache.db entre actualizaciones. Mantén CACHE_DB_PATH=/app/data/cache.db y el mismo nombre de proyecto Compose para reutilizarlo.

~~~sh
docker compose down
~~~

Este comando conserva el volumen. La opción --volumes eliminaría la caché y no forma parte de la parada habitual.

El historial y las tareas continúan en memoria y se pierden al reiniciar, igual que en la aplicación original. Ejecuta una sola instancia.

## Catálogo BEDCA opcional

Coloca `bedca_foods.csv`, `bedca_foodvalues.csv` y `bedca_units.csv` en `bedca/`
o configura `BEDCA_INPUT_DIR`. Con una imagen que incluya la versión 1.13.0:

~~~sh
docker compose --profile catalog run --rm catalog-import
~~~

Después activa `CATALOG_ENABLED=true` en `.env` y arranca el servicio. El catálogo
se guarda en `estimator-catalogs`; la aplicación lo monta en solo lectura y la
caché continúa en `estimator-cache`. Para Decisions configura también
`DECISIONS_ENABLED=true` y `OPENAI_API_KEY`. El fallback LLM conserva su
configuración independiente.

[Instrucciones completas y actualización segura](../docs/11-catalogos-duckdb.md).

## Variables y ejemplo

.env.example incluye todas las variables de configuración del servicio y los dos puertos del despliegue. .env se ignora en el repositorio y contiene tu configuración real.

Los valores iniciales de OFF y del proveedor/modelo LLM siguen el Compose principal del proyecto. El LLM permanece deshabilitado hasta configurarlo. [Cómo carga Compose las variables desde env_file](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).
