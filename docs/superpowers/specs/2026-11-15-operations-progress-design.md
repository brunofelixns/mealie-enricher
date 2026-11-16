# Progreso de Mercadona y panel de operaciones

El usuario solicita implementar un endpoint de progreso y ampliar la vista existente
para consultar estados y ejecutar las operaciones GET/POST sin clientes externos.
La creación de una tarea separada falló en `codex_app/list_projects`; se implementa
en el checkout actual, conservando los cambios sin publicar ni desplegar.

## Diseño

- Mantener FastAPI, Jinja y JavaScript sin dependencias de frontend nuevas y conservar
  el historial y los colores de Mealie.
- Instrumentar la adquisición real: selección del código postal, categorías,
  productos, publicación del catálogo y revisión de recetas. Los contadores proceden
  de peticiones terminadas; un porcentaje desconocido se muestra indeterminado.
- Publicar `GET /pricing/progress`, protegido como los controles existentes, con
  contadores, porcentaje, tiempos y última actividad. Guardar checkpoints limitados
  y emitir logs periódicos sin productos/precios inventados ni secretos.
- Conservar el último catálogo válido y comunicar fallos e interrupciones sin
  presentar una descarga incompleta como terminada.
- Ampliar `/estimator/history` con controles para `/health`, historial JSON (since,
  limit, offset), `/estimate`, `/backfill`, `/webhook`, estado/progreso de precios,
  sincronización y revisión normal o forzada. Mostrar aceptación asíncrona,
  resultados y errores; impedir envíos duplicados desde el panel.
- Permitir controles de precios desde el mismo origen con Bearer válido y seguir
  rechazando otros orígenes. El usuario introduce el token; nunca se inserta la
  configuración secreta en HTML ni se guarda en almacenamiento del navegador.
- Mantener accesibilidad de formularios, progreso indeterminado, estados vacíos,
  errores de conexión y diseño utilizable en móvil.

## Alternativas y decisión de implementación

Se usa polling del endpoint protegido cada pocos segundos, siguiendo el historial
existente. SSE añadiría conexiones persistentes y autenticación distinta sin ser
necesario para el ritmo de descarga actual. Se amplía la página existente en lugar
de introducir otra aplicación. Estas son decisiones de implementación tomadas
dentro de la solicitud explícita de aplicar el cambio.

## Aceptación

Una descarga simulada de dos productos permite observar 1/2 antes de finalizar.
Los controles funcionan desde el origen de la página y rechazan orígenes ajenos;
el HTML no contiene tokens. La vista permite las operaciones documentadas y
distingue `202 accepted` de trabajo terminado. Las pruebas existentes de catálogo,
precios, rutas e historial siguen pasando con el cambio intencionado de interfaz.
