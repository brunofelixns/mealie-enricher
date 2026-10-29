# Etiquetas en español y vista de actividad

## Cambio solicitado

El usuario solicita etiquetas automáticas en español para su instalación de Mealie. Es una diferencia autorizada respecto a los nombres ingleses de la referencia; las reglas nutricionales y los umbrales se conservan.

## Etiquetas automáticas

| Nombre anterior | Nombre actual | Regla |
|---|---|---|
| Calories:Light | Calorías:Bajas | Menos de 350 kcal por ración |
| Calories:Moderate | Calorías:Moderadas | De 350 a 600 kcal por ración, ambos incluidos |
| Calories:Hearty | Calorías:Altas | Más de 600 y hasta 850 kcal por ración |
| Calories:Heavy | Calorías:Muy altas | Más de 850 kcal por ración |
| Digest:Easy | Digestión:Fácil | Menos del 30 % de energía procedente de grasa y hasta 600 kcal |
| Digest:Slow | Digestión:Lenta | Al menos el 40 % de energía procedente de grasa |
| Digest:Moderate | Digestión:Moderada | Resto de casos con kcal y grasa conocidas |
| Digest:Unknown | Digestión:Desconocida | Kcal o grasa desconocidas |

Si las kcal son desconocidas, se omite la etiqueta de calorías, igual que antes. Los casos numéricos especiales conservan la semántica de la referencia.

Los nombres se envían a Mealie, que devuelve sus identificadores y slugs. El servicio conserva esos valores de la API; no calcula los identificadores de las etiquetas.

## Recetas que ya tenían etiquetas inglesas

Cuando un webhook o un backfill vuelva a procesar una receta con el mismo hash, las etiquetas inglesas registradas en calorie_estimator_tags se consideran pendientes de actualizar. Se utilizan los nutrientes ya guardados para obtener las etiquetas españolas y se actualizan tags/extras, sin enviar nutrition ni consultar OFF/LLM por el cambio de idioma.

Se conservan las etiquetas del usuario, incluidas las inglesas que no figuren entre las etiquetas automáticas registradas. Las asociaciones antiguas se retiran de esa receta; las etiquetas globales del catálogo Mealie no se borran.

En la siguiente ejecución, si hash y etiquetas ya están completos, vuelve a aplicarse la omisión habitual. No se ha ejecutado un backfill sobre una instancia del usuario.

## Vista web existente

Con el puerto publicado por defecto, la página es:

~~~text
http://DIRECCION-DEL-SERVICIO:8000/estimator/history
~~~

En ejecución local: [abrir historial](http://localhost:8000/estimator/history). Si se configura otro PUBLISHED_PORT en Docker, sustituir el puerto.

La vista muestra:

- Fecha, origen del evento y receta, con enlace a Mealie.
- Estado de procesamiento, cambios aplicados y duración.
- Nutrientes estimados por ración, con detalle desplegable.
- Errores registrados mientras la entrada exista en el historial.
- Filtros por origen y estado; actualización cada dos segundos.
- Tema claro/oscuro y colores procedentes de Mealie.

El JSON para consultar la misma actividad está en /estimator/history.json. El historial sigue en memoria: 200 entradas por defecto, TTL de 24 horas y pérdida al reiniciar. Su contenido es actividad del enriquecedor, no los logs completos del servidor Mealie.

Para datos sintéticos de demostración puede utilizarse DEV_SEED_HISTORY=true; esos ejemplos se conservan como caracterización de la referencia.

## Validación

Las 21 combinaciones de frontera del original se contrastan con los nombres españoles solicitados. Las grabaciones originales no se modifican: las pruebas aplican únicamente la correspondencia de nombres/slugs al resultado esperado.

Se añaden escenarios de webhook y backfill con etiquetas antiguas: verifican sustitución, conservación de etiquetas del usuario y extras/hash, ausencia de patch nutricional o llamadas OFF/LLM y omisión posterior. El E2E Docker comprueba los nombres que devuelve Mealie real de prueba.

Los resultados ejecutados se registran en el documento 06.
