# Pruebas ampliadas con Mealie real aislado

Fecha: 2026-11-01 (Europe/Madrid).

## Alcance

Se amplía la validación con 14 escenarios contra Mealie v3.19.2 y el servicio
Python ejecutados en Docker. Las peticiones y las escrituras en Mealie son
reales: no se intercepta su API. También son reales DuckDB, SQLite, el
importador y los volúmenes del servicio.

El proyecto Compose tiene un nombre aleatorio `enricher-real-*`, puertos
publicados únicamente en `127.0.0.1`, cuenta y recetas temporales y red propia.
OFF apunta al servidor sintético del mismo proyecto; LLM y Decisions están
desactivados. No se carga ninguna clave OpenAI del entorno del usuario.
El catálogo sintético permite comprobar los resultados a mano; una prueba
adicional utiliza los tres CSV reales de BEDCA disponibles localmente.

## Escenarios

| Escenario | Resultado esperado en Mealie |
|---|---|
| Arroz crudo, 200 g y 2 raciones | 360 kcal y 8 g de proteína por ración, referencia `bedca:1` |
| Arroz cocido, 200 g y 2 raciones | 120 kcal y 3 g de proteína por ración, referencia `bedca:2` |
| Cambiar nota y número de raciones | El webhook recalcula 60 kcal y cambia el hash; el siguiente evento se omite |
| Etiquetas antiguas en inglés | Se sustituyen por las españolas; se conservan nutrición, descripción, extras y etiqueta personal |
| Calorías manuales | El webhook conserva 777 kcal; una estimación explícita aplica el cálculo solicitado |
| Mililitros sin masa conocida | Se limpian nutrientes automáticos anteriores; no se supone que ml equivalen a g |
| Unidades sin peso conocido | Mismo tratamiento conservador; ingrediente sin correspondencia cuantificable |
| Eliminar todos los ingredientes | Se borran nutrición automática y referencias anteriores |
| Ingrediente conocido más ambiguo | Se conserva la suma parcial heredada y se registra el ingrediente pendiente |
| Backfill de tres recetas | Calcula la resuelta, conserva la manual y deja desconocida la ambigua |
| Receta inexistente | El historial muestra el 404 real; una petición posterior válida funciona |
| Reiniciar el servicio | Persisten Mealie, catálogo y caché; el historial en memoria se reinicia |
| Actualizar el catálogo | Rechaza sobrescritura implícita; con `--replace`, un webhook guarda 400 kcal de la nueva versión |
| Exportación BEDCA real | Importa los CSV locales y guarda 384 kcal, 8 g de proteína y referencia `bedca:904` |

Los valores de arroz sintético son datos de prueba, no valores nutricionales
recomendados. Para la ficha real 904, la fuente contiene 1.607,11 kJ y 7,5 g de
proteína por 100 g: 200 g entre dos raciones producen 384 kcal y 8 g tras el
redondeo entero heredado. Se comprueba la transferencia y el cálculo a partir de
la fuente, no la calidad nutricional científica de toda BEDCA.

## Ejecución reproducible

Requiere Docker Desktop iniciado y las imágenes locales ya construidas o
descargadas. Se usa `--pull never` para probar exactamente las imágenes locales;
las pruebas no publican ninguna imagen.

```powershell
$env:RUN_DOCKER_SMOKE = '1'
uv run pytest tests/integration/test_mealie_real.py -q
```

La exportación real es externa, no se incluye en Git y no se descarga desde las
pruebas. Para incluir el escenario real, además de los 13 sintéticos:

```powershell
$env:RUN_REAL_BEDCA = '1'
# Opcional: otra carpeta con los tres CSV de la misma exportación.
$env:BEDCA_REAL_TEST_DIR = 'E:/GitHub/mealie-enricher/data/bedca'
uv run pytest tests/integration/test_mealie_real.py -q --junitxml=.cache/mealie-real-results.xml
```

`CATALOG_TEST_IMAGE` permite cambiar la imagen local de la aplicación; por defecto
se usa `mealie-enricher:catalog-1.13.0`. Los CSV del usuario se montan en solo
lectura; únicamente se sustituye el catálogo del volumen temporal. Al terminar,
se eliminan los contenedores, red y volúmenes del proyecto aleatorio propio.
No se ejecuta ninguna limpieza global de Docker.

## Resultados

- Nuevos escenarios: **14 correctos en 123,74 s**, incluido BEDCA real.
- Regresión Docker anterior: **3 correctas en 67,55 s**; en total, **17 pruebas
  Docker correctas** entre ambas ejecuciones.
- La exportación real importada contiene **957 alimentos y 31.166 componentes**.
  Mealie devuelve 384 kcal, 8 g de proteína y `bedca:904` para la receta de prueba.
- Suite ordinaria: **334 correctas y 17 Docker omitidas en 45,33 s**.
  Las 14 omisiones nuevas corresponden a los escenarios opcionales de este documento.
- Ruff y formato correctos; mypy correcto en los 45 archivos de producción.
- Se utiliza la imagen local de aplicación
  `sha256:c5efbe149491e0597d89b38e7a62f9272f9d4c9d0ccfbc8aedccc5dd4e5e6961`.
  No se ha modificado el código de producción.
- Informe JUnit local en `.cache/mealie-real-results.xml`, ignorado por Git.
  La regresión anterior genera `.cache/docker-regression-results.xml`.
- Comprobación posterior: no quedan contenedores, redes ni volúmenes de los
  proyectos temporales `enricher-real-*`, `enricher-smoke-*` y `enricher-catalog-*`.

El primer intento no llegó a la aplicación: la red marcada como `internal`
impedía acceder a los puertos publicados desde este Docker Desktop en Windows.
El entorno utiliza ahora una red Compose propia normal y los puertos de prueba
en loopback. Con ese ajuste pasan los 14 escenarios.

Estas pruebas validan las escrituras HTTP reales en Mealie y los cálculos locales.
No llaman a OpenAI ni acreditan una conexión positiva con Decisions en vivo;
esa comprobación continúa pendiente de una clave aceptada.
