# Validación adicional de catálogos

Fecha: 2026-11-01 (Europe/Madrid).

## Objetivo

Validar la ampliación SQLite/DuckDB/BEDCA y Decisions desde sus flujos completos.
Se mantiene el comportamiento implementado; los componentes aislados ya tienen
pruebas. Esta ampliación comprueba sus conexiones y la operación entre arranques.

## Base comprobada

Antes de añadir escenarios: 318 pruebas correctas y 3 Docker omitidas;
cobertura de líneas global del 95 % (1.863/1.952). El informe detallado se genera
localmente en `.cache/coverage-validation-before.json`, fuera de Git.

## Escenarios que se añaden

| Escenario | Comprobación observable |
|---|---|
| HTTP → SDK OpenAI → selección → Mealie | IDs restringidos, nutrientes del catálogo y raciones calculadas en Python |
| Abstención, rechazo, HTTP 401/429 y timeout | Sin sustitución por OFF/LLM y sin conservar calorías automáticas anteriores |
| Recuperación después de un fallo | Una nueva estimación explícita vuelve a consultar el selector |
| Reinicio del servicio | Caché SQLite reutilizada, catálogo DuckDB intacto y cliente SDK cerrado |
| Cambio de contexto | Una nota diferente invalida la selección guardada |
| Nueva versión de catálogo | El webhook recalcula en lugar de reutilizar nutrientes de la versión anterior |
| Error al publicar una importación | El catálogo anterior sigue utilizable y se limpian temporales |
| Arranque incompleto | Un fallo de configuración libera el lector de DuckDB |
| Alimento sin ficha en BEDCA | Se conserva el fallback original a Open Food Facts |
| Volumen o unidades sin peso conocido | No se convierten automáticamente a gramos |
| Calorías manuales | El webhook las conserva sin consultar Decisions |

OpenAI se intercepta en el transporte HTTP del SDK real con una clave sintética;
no se usa ninguna clave personal ni se consume la API. Mealie se simula en la
suite ordinaria. Las pruebas Docker utilizan Mealie real en un proyecto temporal,
sin acceder a la instalación del usuario. No se descarga ni redistribuye BEDCA
real desde las pruebas ordinarias: los CSV son sintéticos.

## Ejecución

```powershell
uv run pytest tests/integration/test_catalog_workflows.py tests/integration/test_catalog_operations.py -q
uv run pytest -q --cov=mealie_enricher --cov-report=term-missing:skip-covered
$env:RUN_DOCKER_SMOKE = '1'
uv run pytest tests/integration/test_docker_smoke.py tests/integration/test_catalog_docker.py -q
```

## Resultados

- Se añaden **16 escenarios** en `test_catalog_workflows.py` y
  `test_catalog_operations.py`; todos correctos en su ejecución dirigida.
- Suite completa: **334 pruebas correctas y 3 Docker omitidas**, 30,46 s.
- Cobertura de líneas: **1.866/1.952 = 95,59 %** (pytest muestra 96 % al
  redondear). No se establece un objetivo artificial del 100 %: los nuevos
  escenarios comprueban conexiones y persistencia, además de líneas individuales.
- Ruff correcto: 96 archivos con formato comprobado.
- La ampliación no ha requerido modificar código de producción.
- Mypy correcto en los 45 archivos de producción.
- Docker: **3 pruebas correctas en 75,51 s**, con Mealie real aislado. Incluyen el flujo heredado, BEDCA, limpieza de calorías automáticas, importación y volúmenes separados de caché y catálogo. Se eliminaron los proyectos temporales propios al terminar.

La prueba positiva de OpenAI en vivo sigue pendiente: el intento autorizado del
2026-10-31 recibió AuthenticationError. Los escenarios 401/429 y recuperación de
esta suite son simulados. No acreditan acceso real a un modelo ni disponibilidad
del proveedor.

## Ampliación con Mealie real

La siguiente validación añade 14 escenarios contra el servicio y Mealie reales
en Docker, incluido el procesamiento de los CSV externos de BEDCA disponibles
localmente. [Escenarios, ejecución y resultados](13-pruebas-mealie-real.md).
