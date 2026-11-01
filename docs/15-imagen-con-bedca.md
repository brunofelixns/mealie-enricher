# Imagen Docker con DuckDB y CSV de BEDCA incluidos

## Qué cambia

La variante `bedca` permite arrancar con el catálogo preparado. El mantenedor
importa y valida los CSV al construir la imagen; el usuario configura Mealie y
arranca el servicio. No necesita CSV en el servidor, Python, uv ni un importador.

```text
/opt/bedca/
  catalogos.duckdb
  manifest.json
  NOTICE.md
  source/
    bedca_foods.csv
    bedca_foodvalues.csv
    bedca_units.csv
```

Los CSV conservan sus bytes. El manifiesto registra versión, huellas SHA-256 y
recuentos. DuckDB conserva originales y valores derivados, igual que el
importador existente. Los datos incluidos no son escribibles por `appuser`;
SQLite continúa en su volumen de `/app/data/cache.db`.

Se usa `/opt/bedca` para que el volumen `/app/catalogs` no oculte el catálogo
incluido. La variante activa el catálogo y configura su ruta por defecto.

## Despliegue

Estado de esta entrega: variante construida **localmente** con el tag
`mealie-enricher:bedca`. Esta tarea no publica un nuevo tag en GHCR. Cuando se
publique, configura `MEALIE_ENRICHER_IMAGE` con ese tag o digest verificado.

Usa el [Compose de despliegue](../docker/docker-compose.yml) y copia
[.env.bedca.example](../docker/.env.bedca.example) como `.env`. Configura:

```dotenv
MEALIE_ENRICHER_IMAGE=mealie-enricher:bedca
MEALIE_URL=https://tu-mealie.example.com
MEALIE_API_TOKEN=tu-token
CATALOG_ENABLED=true
CATALOG_DB_PATH=/opt/bedca/catalogos.duckdb
```

Con la imagen local construida:

```sh
docker compose up -d --no-build --pull never --wait calorie-estimator
```

Con una variante publicada, usa `docker compose pull` y después
`docker compose up -d --no-build --wait calorie-estimator`.
No hace falta ejecutar `catalog-import` ni preparar una carpeta `bedca/`.
La configuración de IA sigue siendo opcional e independiente.

## Construcción para mantenedores

Se requieren los tres CSV externos. Desde la raíz, con la imagen base local:

```sh
docker build -t mealie-enricher:catalog-1.13.0 .
docker buildx build --load --network none --build-context bedca_source=./data/bedca --build-arg BASE_IMAGE=mealie-enricher:catalog-1.13.0 --build-arg BEDCA_DATASET_VERSION=bedca-export-2026-08-19 -f docker/Dockerfile.bedca -t mealie-enricher:bedca .
```

El contexto `bedca_source` es explícito: los datos siguen excluidos de Git y del
contexto habitual. Se copian únicamente los tres CSV; otros archivos de esa
carpeta no entran en la imagen. Una exportación inválida hace fallar el build.
La importación se ejecuta sin red y con el DuckDB de la propia imagen base.

Se puede utilizar una base publicada mediante `BASE_IMAGE`; para reproducir una
publicación conviene fijar su digest verificado. La versión del software sigue
siendo la de la base; la versión del dataset se identifica por separado.

## Actualizar y recuperar los originales

Una nueva imagen BEDCA incluye el catálogo nuevo. Al recrear el contenedor, la
aplicación abre esa versión; la firma invalida las selecciones anteriores y
permite recalcular por webhook. SQLite conserva su volumen. No se ejecuta una
migración ni importación de BEDCA durante el arranque.

Para recuperar los CSV originales desde un servicio desplegado:

```sh
docker compose cp calorie-estimator:/opt/bedca/source ./bedca-originales
docker compose cp calorie-estimator:/opt/bedca/manifest.json ./bedca-manifest.json
```

Los originales permanecen en la imagen aunque no se copien al host. Actualizar
la imagen no modifica los archivos exportados previamente. Para usar un catálogo
propio, se mantiene la [preparación de la imagen base](11-catalogos-duckdb.md).

## Condiciones de los datos

El usuario confirma distribución pública **no comercial**. La variante atribuye
los datos a **AESAN/BEDCA Base de Datos Española de Composición de Alimentos
v1.0 (2010)**. Sus condiciones figuran en `/opt/bedca/NOTICE.md` y se identifican
también en las etiquetas OCI. La licencia del código no sustituye las de BEDCA.

Las condiciones oficiales exigen atribución y conservación del significado
original; los usos ajenos al ámbito personal, educativo o no comercial requieren
autorización expresa. Se conservan originales y se distinguen valores derivados;
no se certifica la exactitud nutricional científica de toda la fuente.

- [Condiciones originales AESAN/BEDCA](https://www.bedca.net/bdpub/UsoBD.pdf).
- [Licencia de la exportación](https://github.com/TerjeRu/bedca-database/blob/main/LICENSE).

## Verificación

Verificado el 2026-11-01:

- **358 pruebas correctas en 402,68 s**, sin omisiones: 334 ordinarias y
  24 Docker. La variante añade 7 escenarios al conjunto Docker anterior.
- Comprobados ambos Compose, CSV idénticos byte a byte, manifiesto, atribución,
  permisos, variables por defecto y rechazo de una exportación inválida.
- Arranque con Compose de despliegue y catálogo externo vacío, sin importación.
- Mealie real aislado: guarda 360 kcal con la primera imagen sintética y 400 kcal
  tras actualizarla; cambia el hash y se conserva la caché SQLite.
- Imagen con BEDCA real: 957 alimentos, 31.166 componentes y los tres CSV dentro
  de la imagen. En Mealie, arroz integral crudo devuelve 384 kcal y 8 g de
  proteína por ración, con referencia `bedca:904`, sin montar CSV externos.
- Los SHA-256 de los tres CSV reales extraídos de la imagen coinciden con los
  archivos locales originales; no quedan recursos temporales `enricher-*`.
- Ruff y formato correctos; mypy correcto en 45 archivos de producción.
- Revisión independiente sin hallazgos accionables. No se modifica el código de
  estimación y las pruebas no llaman a OpenAI ni utilizan el Mealie del usuario.
- Los proyectos, volúmenes e imágenes sintéticas temporales se retiran al terminar.
  Se conserva la imagen local real `mealie-enricher:bedca`.

```powershell
$env:RUN_DOCKER_SMOKE = '1'
$env:RUN_REAL_BEDCA = '1'
$env:RUN_BEDCA_IMAGE_REAL = '1'
uv run pytest -q --junitxml=.cache/bedca-bundle-full-results.xml
```

`RUN_REAL_BEDCA` habilita el escenario de CSV reales anterior;
`RUN_BEDCA_IMAGE_REAL` prueba esta nueva imagen real previamente construida.
`BEDCA_BUNDLED_TEST_IMAGE` permite cambiar su tag local. El informe JUnit queda
ignorado por Git. La comprobación local corresponde a **linux/amd64**; no se
acredita aquí publicación de la variante ni ejecución en ARM.

Identificador local de imagen:
`sha256:68926932a1cd81d32358b99fa74ccb9b3a1e02811f52cab7679a434c02dff7f7`.
