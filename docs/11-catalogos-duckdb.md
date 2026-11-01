# Catálogos DuckDB, BEDCA y resolución de alimentos

## Diseño aprobado

El 31 de octubre de 2026 se autoriza implementar la separación propuesta:
SQLite conserva únicamente cachés; DuckDB guarda los catálogos persistentes.
Python mantiene conversiones, sumas, raciones, redondeo y etiquetas. Se conserva
OpenAI Agents SDK para el fallback existente y se añade Decisions como selector
de candidatos, sin generar valores nutricionales del catálogo.

## Comportamiento

- La integración es configurable: sin catálogo habilitado se mantiene el flujo
  compatible del original. Si se habilita, el archivo debe existir y ser válido.
- BEDCA se importa desde CSV externos; no se redistribuye el dataset en Git ni
  en la imagen. Se conservan los registros originales y su procedencia, junto a
  valores derivados con unidades normalizadas. Un desconocido es NULL, nunca 0.
- El catálogo se abre en solo lectura. Un importador construye otro archivo,
  valida, cierra y publica la nueva versión; se activa con reinicio controlado.
- Los candidatos se buscan localmente. Los estados explícitos se respetan;
  Decisions elige exclusivamente un ID ofrecido o `needs_context`. Ambigüedad,
  rechazo, fallo o baja confianza no autorizan a escoger el primer candidato.
- Un alimento encontrado pero ambiguo permanece sin resolver; no se sustituye
  silenciosamente por OFF ni por nutrientes inventados. Si no hay candidatos,
  se conserva el fallback original.
- La caché de selección depende del contexto completo, versión del catálogo y
  configuración de Decisions. No contiene correcciones manuales permanentes.
- Se preparan tablas para productos, presentaciones, tiendas y precios fechados;
  esta fase no recopila datos reales de supermercados ni calcula compras.

## Operación prevista

Importar explícitamente BEDCA con una CLI disponible tanto en uv como dentro de
Docker. La aplicación no descarga ni importa datos durante cada arranque. El
archivo de catálogo vive en un volumen separado de la caché y puede montarse en
solo lectura en el servicio HTTP. La primera preparación es un paso explícito;
los siguientes arranques reutilizan el archivo.

## Preparar BEDCA con uv

Obtén una exportación de [TerjeRu/bedca-database](https://github.com/TerjeRu/bedca-database)
y coloca estos tres archivos juntos en `data/bedca/`:

- `bedca_foods.csv`
- `bedca_foodvalues.csv`
- `bedca_units.csv`

```sh
uv sync --locked
uv run mealie-catalog import-bedca --input-dir data/bedca --output data/catalogs/catalogos.duckdb --dataset-version 2026-08-19
uv run mealie-catalog inspect --catalog data/catalogs/catalogos.duckdb
uv run mealie-catalog search --catalog data/catalogs/catalogos.duckdb --name arroz
```

Alternativa sin entrypoint: `uv run python -m mealie_enricher.catalog.cli` seguido
de los mismos argumentos. La importación no necesita token Mealie ni clave OpenAI.
Si el archivo de salida ya existe, el comando falla; `--replace` autoriza su
reemplazo después de validar completamente el nuevo archivo. Detén lectores antes
de sustituirlo, especialmente en Windows. La huella incluye versión de esquema,
versión declarada del dataset y SHA-256 de los tres CSV.

Activa después `CATALOG_ENABLED=true` y configura `CATALOG_DB_PATH`. Si falta el
archivo o su esquema no es compatible, el servicio no arranca: no continúa
silenciosamente con otra fuente. No hay red ni reimportación durante el arranque.

## Preparar BEDCA con Docker

Desde la raíz del repositorio, configura `BEDCA_INPUT_DIR` con la carpeta de los
tres CSV; el valor inicial es `./data/bedca`. Con la aplicación detenida:

```sh
docker compose build calorie-estimator
docker compose --profile catalog run --rm catalog-import
```

El perfil escribe en el volumen `estimator-catalogs`. El servicio HTTP monta el
mismo volumen en `/app/catalogs` en modo solo lectura. SQLite sigue en
`estimator-cache`, separado del catálogo. Pon `CATALOG_ENABLED=true` en `.env` y:

```sh
docker compose up -d calorie-estimator
```

En la carpeta `docker/`, el mismo perfil utiliza la imagen de
`MEALIE_ENRICHER_IMAGE` y la carpeta inicial de CSV es `./bedca`. No necesita
construir código local; sí una imagen publicada que incluya esta funcionalidad.

Para actualizar una exportación, detén el servicio y ejecuta:

```sh
docker compose stop calorie-estimator
docker compose --profile catalog run --rm catalog-import import-bedca --input-dir /input --output /app/catalogs/catalogos.duckdb --dataset-version VERSION_NUEVA --replace
docker compose up -d calorie-estimator
```

Conserva una copia del catálogo anterior si necesitas volver a esa versión.
`--replace` preserva el archivo anterior si la preparación falla, pero no guarda
un archivo histórico adicional tras una publicación correcta. No uses
`docker compose down --volumes` para actualizar: eliminaría los datos persistentes.

## Decisions y compatibilidad

Configura `DECISIONS_ENABLED=true` y `OPENAI_API_KEY` para usar el selector. Una
clave `DECISIONS_API_KEY` tiene prioridad si necesitas aislar el proyecto. El
modelo inicial es `gpt-6-luna`; la ruta es la Decisions API oficial, no el
endpoint configurable de Mistral/Chat Completions del fallback heredado.

`DECISIONS_MIN_CONFIDENCE` vale 0.9 por defecto y es un umbral operativo inicial,
no una garantía de corrección. `DECISIONS_TIMEOUT_SECONDS=20` acota cola y llamada;
`DECISIONS_MAX_CONCURRENCY=2` limita solicitudes simultáneas. No hay reintentos
automáticos. Las abstenciones y fallos de Decisions no se guardan en caché para
permitir recuperación en una nueva estimación explícita. Tras corregir una
clave, solicita `/estimate` para la receta: un webhook con el mismo hash puede
seguir omitiéndose por la política heredada. Ajustar umbrales requiere casos
etiquetados propios. Las pruebas
ordinarias interceptan las peticiones, no consumen API real ni requieren tu clave.

OpenAI Agents SDK conserva el estimador LLM existente. Decisions complementa ese
flujo mediante el SDK oficial de OpenAI; no se fuerza una herramienta en el
adaptador `LegacyChatModel`, que mantiene su contrato de compatibilidad.

Con catálogo activo, el hash incluye contexto y versión. Si cambia la nota
«crudo/cocido», las instrucciones o el catálogo, se recalcula. Sin catálogo se
mantiene el hash heredado exactamente. Las calorías manuales siguen protegidas.
Los campos calculados que pasan a desconocidos se envían como NULL para no
dejar una estimación automática anterior; el modo heredado no cambia.

Para nutrientes por 100 g, la masa debe conocerse: se aceptan unidades de masa
y conversiones explícitas a masa. No se supone ml=g. El fallback de peso, si
está habilitado, puede estimar cantidades usando el nombre exacto seleccionado.

La procedencia y las ambigüedades se guardan en `extras.calorie_estimator_catalog`
en Mealie. El historial conserva sus contadores de ingredientes encontrados y
pendientes. Los nutrientes siguen en `nutrition` y las categorías en `tags`.
Sodio y colesterol se mantienen en gramos en el contrato interno heredado; no
se modifica silenciosamente el formato que la migración ya enviaba a Mealie.

Se conserva la agregación parcial del original (C22): si falta un nutriente en
un ingrediente y está disponible en otro, el total suma únicamente las
contribuciones conocidas. No debe interpretarse como una composición completa
medida de toda la receta. Si falta en todos, permanece desconocido.

La validación de formato y unidades no certifica la exactitud de la fuente.
Se observó una densidad energética inesperada en el registro BEDCA 2661
(«Arroz, hervido»); se conserva sin corregirlo por una inferencia de IA. Debe
revisarse la ficha original antes de utilizarla como referencia definitiva.

## Supermercados: preparación, sin recopilación en esta fase

El esquema incorpora `products`, `product_nutrients`, `packages`, `retailers`,
`stores` y `price_observations`, inicialmente vacías. Los productos tienen
nutrientes propios con base 100 g/100 ml, sin heredar automáticamente los de un
alimento genérico BEDCA. Los precios tienen presentación, tienda, moneda, fecha,
promoción y procedencia. Aún no hay importador de supermercados, actualización
de precios ni coste de recetas.

## Condiciones de datos

No se incluyen los CSV ni el DuckDB generado en Git o en la imagen. El operador
aporta los datos respetando las condiciones de BEDCA; la aplicación conserva
atribución y originales. Normalizar para cálculos no sustituye los registros
originales ni convierte valores desconocidos a cero. El importador rechaza
duplicados, registros huérfanos, bases/unidades incoherentes y números no finitos.

## Evidencia y estado

- Base inicial: 189 pruebas correctas y 2 pruebas Docker omitidas por defecto.
- Exportación de referencia revisada: 957 alimentos, 31.166 componentes y 69
  combinaciones de unidad/base; contiene W, WKG, VM y D. No es válido asumir
  que todos los nutrientes vienen expresados por 100 g.
- Implementados importador, lector, selección y composición en FastAPI.
- Importación real local: 957 alimentos, 31.166 valores, 69 combinaciones de
  unidad/base. W=30.888, WKG=257, VM=15 y D=6. Los 21 valores VM/D se conservan
  sin convertir a masa; existen 8.294 nutrientes derivados disponibles para el
  contrato actual. Se preservan también los demás componentes originales.
- Prueba real de Decisions: rechazada por autenticación con la clave disponible;
  no se considera validación satisfactoria del proveedor.
- Validación del 2026-10-31: 318 pruebas correctas y 3 casos Docker omitidos en la ejecución ordinaria. Ruff y mypy correctos (45 archivos de fuente). Imagen Docker local 1.13.0 construida; 3 pruebas Docker correctas con Mealie real aislado y datos sintéticos (112,58 s).

La [validación adicional del 2026-11-01](12-validacion-catalogos.md) añade 16
escenarios completos: 334 pruebas ordinarias y 3 Docker correctas.

## Fuentes

- [Exportación BEDCA](https://github.com/TerjeRu/bedca-database).
- [Condiciones BEDCA](https://www.bedca.net/bdpub/UsoBD.pdf).
- [Decisions](https://developers.openai.com/api/docs/guides/decisions).
- [Concurrencia DuckDB](https://duckdb.org/docs/2.0/connect/concurrency).
