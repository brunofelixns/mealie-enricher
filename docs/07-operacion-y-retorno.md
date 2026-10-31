# Operación y retorno al original

Para una instalación a partir de una imagen ya publicada en GHCR, usar [la carpeta docker](../docker/README.md): incluye docker-compose.yml y .env.example para copiar al servidor.

## Cambio de servicio

La migración no ha modificado una instancia Mealie existente ni una caché del usuario. Antes de sustituir el servicio:

1. Conservar la imagen/tag y configuración que usa el original.
2. Detener el original para evitar escrituras concurrentes y obtener su último cache.db exportado.
3. Copiar cache.db a una ubicación de respaldo nueva. Conservar esa copia sin modificaciones.
4. Hacer una segunda copia para Python. No montar la base original directamente.
5. Dar permisos de escritura a uid/gid 1000 en la copia/directorio del contenedor. Puede montarse ese directorio en /app/data sustituyendo el volumen del ejemplo Compose.
6. Reutilizar URL Mealie, tokens, variables OFF/LLM y puerto de la configuración efectiva del servicio anterior. Revisar por separado defaults de código y Compose.
7. Arrancar Python con un proceso, comprobar health e historial y probar una receta conocida.

Alembic se ejecuta al iniciar. Reconoce las tablas heredadas, conserva filas y añade alembic_version. Python escribe SQLite mediante transacciones; no conserva el mecanismo de exportación periódica de sql.js. La prueba de migración compara las filas de una copia generada por el original y verifica persistencia al reabrirla.

## Retorno

1. Detener Python para evitar que ambos servicios procesen el mismo webhook.
2. Restaurar el puerto y contenedor original con la configuración anterior.
3. Usar la copia intacta de la caché anterior si se necesita un retorno limpio.
4. Comprobar health y reactivar el envío de webhooks.

Las escrituras ya hechas sobre recetas Mealie permanecen en Mealie; restaurar la caché no las revierte. El hash y las etiquetas mantienen las reglas del original. Si se necesita revertir una receta, debe utilizarse un respaldo de Mealie; este procedimiento no inventa un undo.

El historial se pierde al detener cada proceso y las tareas en memoria no se recuperan automáticamente. No hay persistencia de jobs ni cambio de estas limitaciones.

## Comprobación LLM real pendiente

Las pruebas ejecutan Agents SDK real con HTTP simulado. Una comprobación con proveedor real requiere la configuración elegida por el usuario: LLM_BASE_URL, LLM_ENDPOINT_URL, LLM_MODEL y LLM_API_KEY. No se ha leído ni utilizado una credencial real.

Cuando se autorice esa comprobación, hacer una única estimación sintética acotada, registrar proveedor/modelo y resultado sin claves, y distinguirla de las pruebas ordinarias. Los fallos siguen devolviendo ausencia de estimación, sin reintentos LLM.

## Catálogos desde 1.13.0

SQLite sigue dedicado a caché y ejecuta Alembic al inicio (revisión 0002). El catálogo DuckDB es un archivo persistente separado, preparado mediante `mealie-catalog import-bedca` o el perfil Docker `catalog-import`. La aplicación lo abre en solo lectura. Véanse la primera preparación, actualización con parada controlada y volúmenes separados en [11-catalogos-duckdb.md](11-catalogos-duckdb.md).

Para volver al flujo anterior, configura `CATALOG_ENABLED=false` y recrea el servicio. La caché heredada se conserva. No elimines volúmenes para cambiar de modo. Las recetas previamente procesadas con catálogo llevan un hash contextual distinto: al volver al modo anterior se volverán a evaluar cuando corresponda; no se revierten automáticamente las escrituras previas de Mealie.

La comprobación real de Decisions se autorizó el 2026-10-31 y devolvió AuthenticationError con la clave disponible. Es independiente del proveedor LLM anterior, cuya prueba real sigue pendiente. Corregir la clave y solicitar una estimación explícita permite reintentar sin esperar el TTL; no se añade reintento automático ni se registra el secreto.
