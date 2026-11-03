# PostgreSQL e historial permanente

La integración requiere la versión **1.3.0 o posterior**, junto con los archivos
Compose y de entorno correspondientes a esa versión.

## Configuración con Docker Compose

Los dos archivos Compose incluyen un servicio `postgres` con PostgreSQL 18,
volumen `estimator-postgres` montado en `/var/lib/postgresql`, comprobación de
disponibilidad y sin puerto publicado en el servidor. La base es exclusiva del
enriquecedor y no modifica la base de Mealie.

Configura en `.env`:

~~~dotenv
POSTGRES_DB=mealie_enricher
POSTGRES_USER=mealie_enricher
POSTGRES_PASSWORD='elige-una-clave-propia'
DATABASE_URL=
HISTORY_MAX_ENTRIES=200
HISTORY_RETENTION_DAYS=0
~~~

Con la URL vacía, Compose conecta al host interno `postgres` y pasa usuario y
contraseña por `PGUSER` y `PGPASSWORD`. No es necesario codificar caracteres
especiales de la contraseña; usa comillas simples en `.env` si contiene `$` o `#`.
El Compose de desarrollo tiene una contraseña de reserva solo para desarrollo;
el de despliegue exige `POSTGRES_PASSWORD`.

Alembic prepara o actualiza las tablas al arrancar. PostgreSQL almacena las
cachés de nutrientes, pesos y resoluciones, además de `execution_history`.
BEDCA permanece en DuckDB y continúa abierto en solo lectura.

## Historial

Cada ejecución conserva su identificador, receta/hogar, origen, fechas, estado,
cambios, nutrientes disponibles y error. La aplicación confirma las escrituras
antes de avanzar en los puntos principales del procesamiento.

- `HISTORY_RETENTION_DAYS=0`: sin eliminación automática.
- Un entero positivo elimina ejecuciones terminadas antiguas al consultar el
  historial o iniciar la aplicación. Las ejecuciones activas no se purgan.
- `HISTORY_MAX_ENTRIES=200`: tamaño inicial de la página y vista en memoria;
  no limita las filas persistidas.
- `GET /estimator/history.json?limit=100&offset=100`: consulta otra página.
- `since` conserva su contrato de milisegundos y filtra por última actualización.
  Sin `limit` explícito devuelve todas las actualizaciones desde esa fecha para
  que el sondeo no pierda cambios al avanzar su marca temporal.
- `limit` admite 1–1000 y `offset` enteros no negativos. La respuesta sigue siendo
  una lista JSON. La interfaz web muestra inicialmente la página más reciente.

Al reiniciar, las ejecuciones que quedaron `running` se marcan `error` con
explicación de interrupción. No se repiten automáticamente las escrituras sobre
Mealie. La cola, los bloqueos por receta y los limitadores siguen en memoria:
esta versión admite **una sola instancia de aplicación**.

## Actualización y compatibilidad

Actualiza conjuntamente la aplicación y Compose. Añade la contraseña a `.env`;
la nueva base se inicializa al arrancar. El volumen SQLite anterior se conserva,
pero no se importa automáticamente: la caché PostgreSQL se poblará al procesar
recetas. El historial que antes existía exclusivamente en memoria no se puede
recuperar. No elimines volúmenes para actualizar.

Fuera de Compose, `DATABASE_URL` acepta `postgresql://`,
`postgresql+psycopg://` y `sqlite+aiosqlite://`. Por ejemplo:

~~~dotenv
DATABASE_URL=postgresql+psycopg://usuario:CLAVE_CODIFICADA@localhost:5432/mealie_enricher
~~~

Cuando una contraseña va dentro de la URL, debe estar codificada como URL.
Una URL SQLite explícita también habilita el historial persistente. Sin
`DATABASE_URL`, se conserva el comportamiento heredado: caché SQLite en
`CACHE_DB_PATH` y 200 entradas de historial en memoria con caducidad de 24 horas.
La aplicación no imprime la URL en su representación de configuración.

En Windows, `python -m mealie_enricher` selecciona un bucle de eventos compatible
con psycopg. Si integras `create_app` en tu propio servidor, usa un
`asyncio.SelectorEventLoop` para PostgreSQL.

Cambiar `POSTGRES_PASSWORD` en `.env` no cambia la contraseña de un rol ya
creado en un volumen existente; la rotación requiere cambiar también ese rol.
Actualizar la versión mayor de PostgreSQL requiere una migración de su base,
no solo sustituir la etiqueta de la imagen.

## Copias de seguridad

Genera un archivo dentro del contenedor y cópialo al servidor; funciona también
en PowerShell sin redirigir datos binarios:

~~~sh
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/enricher.dump'
docker compose cp postgres:/tmp/enricher.dump ./enricher.dump
~~~

Guarda el archivo fuera del volumen y comprueba periódicamente su restauración
en una base aislada. Conserva aparte el catálogo personalizado si utilizas uno.
`docker compose down` conserva los volúmenes; `down --volumes` elimina también
la base de datos y no es una parada habitual.

## Pruebas

`tests/integration/test_database.py` ejecuta el mismo contrato con SQLite y
PostgreSQL. Configura `TEST_POSTGRES_URL` para una base de pruebas: cada caso
crea y elimina su propio esquema con nombre aleatorio, sin reutilizar tablas de
la aplicación. El usuario de pruebas necesita permiso para crear esquemas.
GitHub Actions incluye PostgreSQL para ejecutar estos casos en la suite.

Fuentes: [SQLAlchemy y psycopg](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg),
[migraciones asíncronas Alembic](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic),
[persistencia de PostgreSQL 18 en Docker](https://docs.docker.com/guides/postgresql/immediate-setup-and-data-persistence/).
