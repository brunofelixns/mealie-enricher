# Migración de Mealie Calorie Estimator a Python

[English README](../README.md) · [Presentación en español](README.es.md) · [Despliegue en español](../docker/README.es.md)

Fecha de apertura: 2026-10-29.

Esta carpeta conserva el alcance, las decisiones, el diseño y el avance de la migración. El objetivo es reproducir el comportamiento y las limitaciones del servicio original en Python.

## Estado actual

- Plan aprobado para ejecución el 2026-10-29.
- Fase 0 completada: referencia fijada, typecheck correcto y 140 pruebas upstream aprobadas.
- 125 capturas reproducibles, 40 contratos identificados y una base de caché heredada generados.
- Fases 0–8 completadas: 187 pruebas Python y 2 Docker aprobadas, cobertura 95 %, revisión final corregida. Agents SDK verificado con transporte simulado.
- Proveedor LLM real, CI remoto y publicación de imagen en GHCR sin ejecutar.
- Adaptación posterior D07: etiquetas automáticas en español; 189 pruebas Python y 2 Docker aprobadas. Reglas y umbrales conservados.
- Código publicado en [brunofelixns/mealie-enricher, rama main](https://github.com/brunofelixns/mealie-enricher/tree/main), con README visual, portada y logo oficial de Mealie.
- [Resultados y evidencia de ejecución](06-resultados-ejecucion.md).

- Ampliación 1.13.0: SQLite solo caché y DuckDB/BEDCA integrados; 334 pruebas ordinarias y 17 Docker correctas, incluidas escrituras reales en Mealie con BEDCA local. Decisions probado con transporte simulado; la prueba real recibió AuthenticationError. [Guía de catálogos](11-catalogos-duckdb.md) y [validación con Mealie real](13-pruebas-mealie-real.md).

## Lectura recomendada

| Documento | Contenido |
|---|---|
| [01-alcance-y-decisiones.md](01-alcance-y-decisiones.md) | Objetivo, tecnologías y decisiones vigentes |
| [02-arquitectura.md](02-arquitectura.md) | Módulos, flujo e integración con Agents SDK |
| [03-compatibilidad-y-validacion.md](03-compatibilidad-y-validacion.md) | Contratos que conservar y cómo comprobarlos |
| [04-registro-de-progreso.md](04-registro-de-progreso.md) | Historia de decisiones y evidencia de avance |
| [05-plan-de-implementacion.md](05-plan-de-implementacion.md) | Tareas ordenadas, dependencias y verificaciones |
| [06-resultados-ejecucion.md](06-resultados-ejecucion.md) | Evidencia de pruebas, contenedores y límites de verificación |
| [07-operacion-y-retorno.md](07-operacion-y-retorno.md) | Arranque, copia de caché y retorno al original |
| [08-revision-y-resoluciones.md](08-revision-y-resoluciones.md) | Revisión final, decisiones de ejecución y límites |
| [09-etiquetas-y-vista-web.md](09-etiquetas-y-vista-web.md) | Etiquetas en español y consulta de la actividad |
| [10-publicacion-github.md](10-publicacion-github.md) | Primera publicación del código y recursos del README |
| [11-catalogos-duckdb.md](11-catalogos-duckdb.md) | BEDCA, catálogos DuckDB, Decisions y preparación con Docker |
| [12-validacion-catalogos.md](12-validacion-catalogos.md) | Pruebas del flujo completo, reinicios, actualización y recuperación |
| [13-pruebas-mealie-real.md](13-pruebas-mealie-real.md) | Escenarios HTTP reales con Mealie aislado y exportación BEDCA local |
| [../docker/README.md](../docker/README.md) | Descargar, configurar y ejecutar la imagen publicada en GHCR |
| [referencias/propuesta-inicial.md](referencias/propuesta-inicial.md) | Copia del texto adjunto aportado por el usuario |

## Fuente de la migración

- Repositorio: [timo-reymann/mealie-calorie-estimator](https://github.com/timo-reymann/mealie-calorie-estimator).
- Referencia revisada: [c2dc71a1d8effe29375391f2fe50da94d27cfd7d](https://github.com/timo-reymann/mealie-calorie-estimator/tree/c2dc71a1d8effe29375391f2fe50da94d27cfd7d).
- Versión declarada en esa referencia: 1.12.3.
- Carpeta de destino: E:\GitHub\mealie-enricher.

## Cómo mantener la documentación

1. Registrar decisiones nuevas en el documento 01 y su motivo en el documento 04.
2. Actualizar el diseño y la matriz de compatibilidad si una decisión los afecta.
3. Marcar una tarea del plan como terminada únicamente después de ejecutar su verificación.
4. Anotar comando, resultado y alcance de cada comprobación en el documento 04.
5. Distinguir pruebas con respuestas simuladas, integración local y proveedor real.
6. Mantener el adjunto como referencia histórica; no utilizar sus alternativas opcionales como requisitos aprobados.

La ejecución del plan está autorizada; los estados anteriores describen exclusivamente lo verificado.
