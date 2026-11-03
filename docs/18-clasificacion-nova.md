# Etiqueta NOVA con OpenAI Decisions

La familia NOVA estima el procesamiento de los ingredientes de una receta.
Es opcional y no utiliza las calorías, la grasa ni la digestibilidad para
deducir un grupo. La nutrición sigue calculándose por el flujo existente.

## Activación

Configura `NOVA_ENABLED=true` en el entorno del enriquecedor y reinicia el
servicio con una versión que contenga esta función. Reutiliza la clave existente:
`DECISIONS_API_KEY` tiene prioridad sobre `OPENAI_API_KEY`. No se copia ni se
reutiliza `LLM_API_KEY`, que puede corresponder a otro proveedor.

Se aplican `DECISIONS_MODEL` (por defecto `gpt-6-luna`),
`DECISIONS_MIN_CONFIDENCE` (0,9), `DECISIONS_TIMEOUT_SECONDS` (20) y
`DECISIONS_MAX_CONCURRENCY` (2 llamadas simultáneas del clasificador NOVA).
El timeout incluye la espera de capacidad; no hay reintentos automáticos del SDK.
No requiere `CATALOG_ENABLED`, `DECISIONS_ENABLED` ni `LLM_ENABLED`.
Con NOVA activo y sin clave, el inicio falla con un error de configuración.
Con `NOVA_ENABLED=false`, valor inicial, no se hacen llamadas NOVA.

## Grupos y criterio para recetas

| Etiqueta | Significado de la estimación |
|---|---|
| `NOVA:1` | Alimentos no procesados o mínimamente procesados; preparación casera basada en ellos. |
| `NOVA:2` | Preparación formada únicamente por ingredientes culinarios procesados, como aceite, sal, azúcar o mantequilla. |
| `NOVA:3` | Presencia acreditada de alimentos procesados, sin evidencia de grupo 4. |
| `NOVA:4` | Presencia acreditada de una formulación o ingrediente ultraprocesado. |
| `NOVA:Desconocida` | Evidencia insuficiente, confianza baja, rechazo o error del proveedor. |

NOVA clasifica alimentos. **Asignar una sola etiqueta a una receta mixta es una
regla de esta aplicación, no un método oficial de puntuación NOVA de recetas.**
Decisions recibe la instrucción de elegir el mayor grupo acreditado entre los
ingredientes tal como se incorporan, con una excepción: añadir aceite, sal o
azúcar de grupo 2 a alimentos de grupo 1 al cocinar en casa no eleva por sí solo
la receta a grupo 2 o 3. Hervir, cortar, asar o congelar tampoco la hace
ultraprocesada. No se pondera por masa ni por calorías.

Por ejemplo, una ensalada de tomate con aceite y sal puede estimarse como grupo 1;
una receta con queso simple puede contener grupo 3; una receta con un producto
cuya formulación acredita ultraprocesamiento puede recibir grupo 4. Son ejemplos
del criterio enviado al modelo, no garantías de su respuesta para cualquier texto.
Los nombres genéricos de salsas, caldos, panes o preparados cárnicos pueden ser
ambiguos. El modelo no debe inventar marcas, aditivos o composición para resolverlos.
Un ingrediente sin resolver que pudiera elevar el grupo exige `needs_context`.

## Datos enviados, resultados y caché

La API oficial recibe nombre, descripción, ingredientes (incluido `originalText`)
e instrucciones de la receta. No se envían etiquetas, extras, tokens de Mealie ni
nutrición. Los textos se tratan como datos, no como instrucciones del clasificador.
Se formula una pregunta `choice` con cinco opciones cerradas: los grupos 1–4 y
`needs_context`. La aplicación valida nombre, tipo, opción y confianza numérica
finita antes de aceptar un grupo. Una receta sin evidencia de ingredientes se
marca desconocida sin llamar al proveedor.

`extras.calorie_estimator_nova` guarda un JSON con grupo, confianza, estado,
modelo, huella del contexto, firma de configuración/política y slug de etiqueta.
`tag_status` diferencia la evaluación pendiente de aplicar (`unresolved`),
la etiqueta aplicada (`applied`) y una etiqueta no disponible en Mealie (`unavailable`).
La etiqueta se registra entre las automáticas en `calorie_estimator_tags`.
Las etiquetas personales, otros extras y los ingredientes se conservan.

Webhook y backfill añaden NOVA aunque las etiquetas nutricionales anteriores ya
estuvieran completas. Si el hash nutricional no cambia, se actualizan únicamente
etiquetas y extras. Cambiar nombre, descripción, ingredientes o instrucciones
invalida la evaluación NOVA; cambiar sus propias etiquetas no lo hace. Los cambios
de modelo, umbral o política también invalidan la evaluación. Si solo falta la
etiqueta, se repara desde la evaluación guardada. La primera confirmación de
calorías manuales puede añadir NOVA sin modificar esas calorías.

Los resultados desconocidos, incluidos errores y rechazos, también se guardan
para evitar bucles de llamadas tras los webhooks generados por el propio patch.
Se reintentan cuando cambia el contexto/configuración o mediante `/estimate`.
**`/estimate` fuerza el flujo completo de estimación nutricional existente**, no
es un endpoint exclusivo para NOVA y conserva su comportamiento de sobrescritura.
Un fallo de Decisions no impide completar la estimación nutricional: produce la
etiqueta desconocida y un estado de evaluación en extras. Los logs muestran el
tipo de error, sin imprimir cuerpos del proveedor ni claves.

Si Mealie no permite crear ni recuperar la etiqueta NOVA, la evaluación se guarda
con `tag_status=unavailable` y sin apropiarse del slug de otra etiqueta. La
nutrición puede completarse; los webhooks del propio patch no provocan un bucle.
Cambiar el contexto o forzar `/estimate` vuelve a intentar aplicar la etiqueta.

## Fuentes

- [FEAD: clasificación NOVA](https://saludigestivo.es/alimentacion-saludable/clasificacion-nova/): definiciones de los cuatro grupos y ejemplos.
- [Open Food Facts: NOVA](https://es.openfoodfacts.org/nova): referencia solicitada; su página bloqueó la lectura automatizada durante esta implementación.
- [Esquema oficial de Open Food Facts](https://openfoodfacts.github.io/documentation/docs/Product-Opener/schemas/schemas/product/): `nova_group` identifica un grupo entero de 1 a 4 para un producto.
- [OpenAI Decisions](https://developers.openai.com/api/docs/guides/decisions): preguntas con opciones cerradas, confianza y abstención.

No se consulta una ficha de producto de Open Food Facts para justificar esta
etiqueta: se trata de una inferencia del contexto de Mealie. La confianza del
modelo no convierte esa inferencia en una certificación ni en una valoración
nutricional del plato.

## Validación de esta implementación

Validación local del 3 de noviembre de 2026: **562 pruebas correctas, 27 omitidas
por sus opciones de integración y 96,18 % de cobertura**. Ruff, formato, mypy y
la validación del Compose de desarrollo pasan. Las pruebas de Mealie utilizan
transportes HTTP simulados; no se ha ejecutado un backfill ni un despliegue real.

Cinco ejemplos sintéticos se enviaron a la API real de Decisions con la clave
existente autorizada: se aceptaron los grupos 1, 2 y 3; una salsa sin composición
devolvió `needs_context`; un refresco obtuvo 0,71 de confianza y permaneció
desconocido por el umbral de 0,9. La aceptación de grupo 4 está cubierta con el
transporte simulado. Estos ejemplos verifican la integración y su abstención,
sin medir la precisión general del clasificador.
