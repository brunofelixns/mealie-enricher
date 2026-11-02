# Imagen Docker con DuckDB y CSV de BEDCA incluidos

## Qué cambia

Desde **1.2.0**, la imagen normal (`latest` o un tag de versión) incluye el
catálogo preparado. El mantenedor importa y valida los CSV al construirla;
el usuario configura Mealie y arranca el servicio. Una sola imagen contiene
aplicación, DuckDB, originales y atribución.

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
incluido. La imagen activa el catálogo y configura su ruta por defecto.

## Despliegue

El workflow publica una imagen mediante `latest` y `X.Y.Z`, después de pasar
toda la suite. Los alias antiguos `bedca` y `latest-bedca` apuntan a ese mismo
digest; no son imágenes distintas. Desde 1.2.0 no se publican tags `X.Y.Z-bedca`.
Las versiones anteriores conservan su contenido. [Flujo automático](16-github-actions.md).

Usa el [Compose de despliegue](../docker/docker-compose.yml) y copia
[.env.example](../docker/.env.example) como `.env`. Configura:

```dotenv
MEALIE_ENRICHER_IMAGE=ghcr.io/brunofelixns/mealie-enricher:latest
MEALIE_URL=https://tu-mealie.example.com
MEALIE_API_TOKEN=tu-token
CATALOG_ENABLED=true
CATALOG_DB_PATH=/opt/bedca/catalogos.duckdb
```

Con una imagen construida localmente, configura `MEALIE_ENRICHER_IMAGE=mealie-enricher:local` y:

```sh
docker compose up -d --no-build --pull never --wait calorie-estimator
```

Con una imagen publicada, usa `docker compose pull` y después
`docker compose up -d --no-build --wait calorie-estimator`.
No hace falta ejecutar `catalog-import` ni preparar una carpeta `bedca/`.
La configuración de IA sigue siendo opcional e independiente.

## Construcción para mantenedores

Se requieren los tres CSV externos, también con `CATALOG_ENABLED=false`:
desactivar el catálogo al arrancar no cambia el contenido de la imagen.
Obtén los archivos `output/bedca_foods.csv`, `output/bedca_foodvalues.csv` y
`output/bedca_units.csv` de la [revisión fija de la exportación](https://github.com/TerjeRu/bedca-database/tree/3e4e0c180267bb158564a03cff1cca510ecb8135/output),
cópialos a `data/bedca/` y verifica sus SHA-256 con `ci/bedca.sha256`.
En Linux, desde la raíz, puedes comprobarlos con
`sha256sum --strict --check ci/bedca.sha256`; en PowerShell, usa
`Get-FileHash data/bedca/*.csv -Algorithm SHA256` y compara los tres valores.
El workflow realiza estos pasos mediante la acción `prepare-bedca`.
Después se construye una sola imagen:

```sh
docker buildx build --load --build-context bedca_source=./data/bedca --build-arg BEDCA_DATASET_VERSION=bedca-export-2026-08-19 -t mealie-enricher:local .
```

El contexto `bedca_source` es explícito: los datos siguen excluidos de Git y del
contexto habitual. Se copian únicamente los tres CSV; otros archivos de esa
carpeta no entran en la imagen. Una exportación inválida hace fallar el build.
La importación se ejecuta sin red y con el DuckDB del runtime preparado en una
etapa interna. La imagen sin datos es únicamente una etapa de construcción.

`docker/Dockerfile.bedca` se conserva como fixture interna para comprobar el
reemplazo de catálogos y para construcciones históricas. El pipeline actual
publica exclusivamente el Dockerfile principal. Software y dataset mantienen
sus versiones separadas.

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
propio, se mantiene la [preparación de catálogos propios](11-catalogos-duckdb.md).

## Condiciones de los datos

El usuario confirma distribución pública **no comercial**. La imagen atribuye
los datos a **AESAN/BEDCA Base de Datos Española de Composición de Alimentos
v1.0 (2010)**. Sus condiciones figuran en `/opt/bedca/NOTICE.md` y se identifican
también en las etiquetas OCI. La licencia del código no sustituye las de BEDCA.

Las condiciones oficiales exigen atribución y conservación del significado
original; los usos ajenos al ámbito personal, educativo o no comercial requieren
autorización expresa. Se conservan originales y se distinguen valores derivados;
no se certifica la exactitud nutricional científica de toda la fuente.

- [Condiciones originales AESAN/BEDCA](https://www.bedca.net/bdpub/UsoBD.pdf).
- [Licencia de la exportación](https://github.com/TerjeRu/bedca-database/blob/main/LICENSE).

## Verificación histórica de la variante 1.0.0

Verificación anterior al ajuste de numeración a 1.0.0 (2026-11-01):

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
  Se conserva la imagen local real `mealie-enricher:1.0.0-bedca`.

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

Identificador de la imagen usada en aquella ejecución:
`sha256:68926932a1cd81d32358b99fa74ccb9b3a1e02811f52cab7679a434c02dff7f7`.

## Numeración propia 1.0.0

Por indicación del usuario, Mealie Enricher utiliza **1.0.0**. Se reconstruyen
las imágenes locales `mealie-enricher:1.0.0` y `mealie-enricher:1.0.0-bedca`;
en ambas, el paquete instalado y la etiqueta OCI indican 1.0.0. Los comandos
anteriores utilizan estos nombres vigentes. La versión del dataset permanece
independiente y los CSV no cambian.

La ejecución completa de 358 pruebas anterior conserva su numeración y digest
históricos. Tras ajustar la versión se ejecuta una nueva validación, registrada
en [resultados](06-resultados-ejecucion.md). Ese ajuste de numeración no publicó un nuevo tag. El workflow añadido después
gestiona las publicaciones y versiones automáticamente; véase el documento 16.

La variante **1.0.0-bedca** ya está publicada en GHCR, también mediante los
aliases `bedca` y `latest-bedca`, para amd64 y arm64. La comprobación pública y
los digests están registrados en [GitHub Actions](16-github-actions.md).
