[English](README.md) | **Español**

# Ejecutar la imagen publicada en GitHub

Esta carpeta permite descargar y ejecutar Mealie Enricher desde **GitHub Container Registry (GHCR)**. Solo necesitas Docker con Compose y estos tres archivos; la instalación no requiere Python, uv ni el código fuente del proyecto.

Main exige PR y pruebas correctas. Release Please propone automáticamente versión y changelog; fusionar su PR publica una imagen completa mediante `latest` y tags de versión para linux/amd64 y linux/arm64. Desde **1.2.0**, todos incluyen BEDCA. [Flujo, versiones y recuperación](../docs/16-github-actions.md).

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
MEALIE_ENRICHER_IMAGE=ghcr.io/brunofelixns/mealie-enricher:latest
MEALIE_URL=https://tu-mealie.example.com
MEALIE_API_TOKEN=tu-token-de-mealie
POSTGRES_PASSWORD=elige-una-clave-privada-para-la-base
~~~

Puedes utilizar exclusivamente tokens por hogar, siguiendo los comentarios de .env.example. Compose carga todas esas variables mediante env_file, sin necesidad de enumerar cada hogar en el YAML.

PUBLISHED_PORT es el puerto del servidor; PORT es el puerto dentro del contenedor. Por ejemplo, PUBLISHED_PORT=8002 y PORT=8000 publican el servicio en el puerto 8002.

MEALIE_URL debe ser accesible desde el contenedor: localhost apuntaría al propio contenedor. Usa la URL de tu servidor Mealie. Si ambos servicios se conectan por nombre de contenedor, deben compartir una red Docker.

El fallback LLM queda deshabilitado inicialmente. Para activarlo, configura LLM_ENABLED=true, LLM_API_KEY y la URL/modelo de tu proveedor. Se conservan las mismas variables de la aplicación.

PostgreSQL, NOVA y precios de supermercados requieren **1.3.0 o posterior**.
La versión `1.2.0` incluye BEDCA sin estas ampliaciones. Actualiza conjuntamente
la imagen y los archivos de despliegue; no uses este Compose con una imagen anterior.

Al actualizar una instalación, incorpora las variables nuevas a tu `.env`
conservando sus tokens, contraseña y valores propios. El antiguo
`.env.bedca.example` también contiene la configuración completa para la misma imagen.

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
MEALIE_ENRICHER_IMAGE=ghcr.io/brunofelixns/mealie-enricher@sha256:DIGEST_PUBLICADO
~~~

El tag o digest debe existir y corresponder a una imagen compatible con la arquitectura del servidor.

## Datos y parada

El servicio `postgres` guarda la caché y el historial en el volumen
`estimator-postgres`. No publica puertos en el servidor y el enriquecedor espera
a que esté preparado. Mantén el nombre del proyecto Compose para reutilizarlo.
La contraseña se pasa mediante `PGPASSWORD`, por separado de la URL, por lo que
admite caracteres especiales sin codificarlos como URL.

~~~sh
docker compose down
~~~

Este comando conserva los volúmenes. La opción `--volumes` eliminaría también la
base PostgreSQL y no forma parte de la parada habitual.

El historial sobrevive a reinicios y no caduca por defecto.
`HISTORY_RETENTION_DAYS=90` elimina ejecuciones terminadas tras 90 días; `0`
conserva todo. `HISTORY_MAX_ENTRIES` determina el tamaño inicial de página, no
el límite de filas guardadas. Puedes consultar páginas anteriores mediante
`/estimator/history.json?limit=200&offset=200`; la interfaz muestra inicialmente
la página más reciente.

Las tareas y los bloqueos siguen en memoria: ejecuta una sola instancia.
Las ejecuciones pendientes guardadas se marcan como interrumpidas al reiniciar,
sin repetir automáticamente escrituras sobre Mealie.

Al actualizar desde una instalación anterior, añade `POSTGRES_PASSWORD` y usa
una imagen que contenga esta integración. Alembic actualiza las tablas al
arrancar. El antiguo volumen SQLite se conserva; la caché no se copia a
PostgreSQL y se vuelve a poblar al procesar recetas. El historial que antes
estaba en memoria no se puede recuperar. Cambiar la clave en `.env` no modifica
la contraseña de un rol PostgreSQL ya creado: hay que cambiarla también en la base.

[Configuración, copias de seguridad y recuperación](../docs/19-postgresql.md).

## Catálogo BEDCA incluido

Desde **1.2.0**, la [imagen normal](../docs/15-imagen-con-bedca.md) conserva DuckDB
y los tres CSV originales para uso no comercial. El ejemplo estándar ya configura
`CATALOG_ENABLED=true` y `CATALOG_DB_PATH=/opt/bedca/catalogos.duckdb`.
`latest` y el tag normal de versión contienen todo; los alias antiguos `bedca`
apuntan al mismo digest.

Si necesitas un catálogo propio, sigue la preparación manual:

Coloca `bedca_foods.csv`, `bedca_foodvalues.csv` y `bedca_units.csv` en `bedca/`
o configura `BEDCA_INPUT_DIR`. Con una imagen que incluya la funcionalidad de catálogos:

~~~sh
docker compose --profile catalog run --rm catalog-import
~~~

Después activa `CATALOG_ENABLED=true`, configura
`CATALOG_DB_PATH=/app/catalogs/catalogos.duckdb` en `.env` y arranca el servicio. El catálogo
se guarda en `estimator-catalogs`; la aplicación lo monta en solo lectura y la
caché y el historial continúan en PostgreSQL. Para Decisions configura también
`DECISIONS_ENABLED=true` y `OPENAI_API_KEY`. El fallback LLM conserva su
configuración independiente.

Para añadir etiquetas NOVA estimadas, configura `NOVA_ENABLED=true` con esa
misma clave y los límites `DECISIONS_*`. Funciona sin activar el selector de
catálogo ni el fallback LLM. Se aplica cuando las recetas vuelven a procesarse;
la nutrición existente se conserva si no ha cambiado su hash. Los resultados
desconocidos se reutilizan hasta que cambie el contexto o se fuerce `/estimate`.
[Criterio, fuentes y reintentos](../docs/18-clasificacion-nova.md).

## Precios de Mercadona

La función viene desactivada. Reutiliza la clave `OPENAI_API_KEY` o
`DECISIONS_API_KEY` configurada y establece estos valores en `.env`, con un token
de administración privado y aleatorio de al menos 16 caracteres:

~~~dotenv
PRICING_ENABLED=true
MERCADONA_POSTAL_CODE=27004
PRICING_SYNC_INTERVAL_HOURS=168
PRICING_AUTO_SYNC=true
PRICING_ADMIN_TOKEN=sustituye-por-tu-token-privado-aleatorio
~~~

El primer arranque descarga el catálogo completo; después se actualiza con el
intervalo configurado. Los productos, versiones de precios y programación quedan
en `/app/data/supermarkets`, dentro del volumen persistente `estimator-cache`,
separados de BEDCA y PostgreSQL. Usa un único propietario de precios para ese
directorio. El ejemplo permite ajustar pausas, límites de productos/candidatos y
presupuesto de Decisions. Los controles `/pricing/status`, `/pricing/sync` y
`/pricing/refresh` exigen `PRICING_ADMIN_TOKEN`, independiente de la clave OpenAI.
[Costes, etiquetas exactas, controles y límites](../docs/20-precios-supermercados.md).

[Instrucciones completas y actualización segura](../docs/11-catalogos-duckdb.md).

## Variables y ejemplo

.env.example incluye todas las variables de configuración del servicio y los dos puertos del despliegue. .env se ignora en el repositorio y contiene tu configuración real.

Los valores iniciales de OFF y del proveedor/modelo LLM siguen el Compose principal del proyecto. El LLM permanece deshabilitado hasta configurarlo. [Cómo carga Compose las variables desde env_file](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).
