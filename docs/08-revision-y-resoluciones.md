# Revisión final y resoluciones de ejecución

Estas resoluciones describen la migración inicial. La inicialización de Git y la subida posterior del código fueron autorizadas después por el usuario y se registran en [publicación en GitHub](10-publicacion-github.md).

## Revisión

Se realizó una revisión independiente, de solo lectura, del conjunto implementado frente al plan y las fuentes originales. No se detectaron hallazgos críticos. Los hallazgos importantes se reprodujeron antes de corregirlos y se verificaron en la suite completa; no se realizó una segunda revisión que sustituyera esas pruebas.

| Hallazgo | Resultado |
|---|---|
| Extras JSON válidos rechazados por el modelo | Se conservan valores anidados y numéricos en lectura/patch |
| Parsing HTTP distinto de Fastify | Capturas de JSON inválido/vacío, media type, texto, null/ausencia y preflight pasan |
| Token de .compose-test.env sobrescrito por vacío | El override de producción se mantiene fuera del anchor común |
| Números como texto alteraban el hash | Texto conservado en hash/yield; coerción JS aplicada en aritmética |
| Timeout HTTPX reiniciado al llegar datos | Deadline total aplicado a Mealie y tema; sin repetir escrituras |
| Redirecciones fetch perdidas | LLM/OFF/tema siguen redirecciones; cliente Mealie conserva no-follow |
| JSON malformado en caché generaba error de receta | Vuelve a ser un miss, igual que el original |

El último se reclasificó de menor a importante por su efecto: una fila recuperable de caché no debe impedir el procesamiento que antes podía continuar. Los aliases estructurados o nulos de alimentos también se admiten, al ser metadatos que el cálculo no utiliza.

## Decisiones tomadas durante la ejecución

Las decisiones siguientes explican cómo se resolvieron conflictos del plan y del entorno. La última columna describe el coste o límite de cada elección, no una incidencia observada.

| Resolución y motivo | Coste o límite |
|---|---|
| Trabajar en el destino explícito sin inicializar Git: era una carpeta nueva | No hay commits/rollback Git automático; el usuario puede versionarla después |
| Probar con proveedores simulados y claves sintéticas; Agents SDK no cambia el proveedor elegido | La conectividad y respuestas de un LLM real siguen sin verificar |
| Añadir áreas llm/off/processing al manifiesto para seleccionar sus casos | El formato de clasificación tiene más áreas que los ejemplos iniciales |
| Acotar Ruff a src/tests/alembic y excluir cachés explícitamente por ausencia de Git | Nuevos directorios de código deberán añadirse al comando de calidad |
| Restaurar dependencias desde el lock tras el recorrido accidental de Ruff; auditar 5204 archivos | Se consumió tiempo de reinstalación; la auditoría no encontró diferencias restantes |
| Usar hogares sintéticos sin colisiones de casing en Windows y comprobar casing en mapping explícito | No reproduce la creación de dos variables solo distintas en mayúsculas en process.env de Windows |
| Ejecutar pruebas asyncio fuera del sandbox que bloqueaba socketpair | La validación requirió permisos adecuados del entorno; no cambia el runtime |
| Integrar history.json en fase 6 y dejar HTML/tema en fase 7 | Cambia el orden de entrega interno; el resultado final es el mismo |
| Conservar el ledger temporal al no existir historial Git | Quedan logs locales ignorados en .superpowers |
| Usar nombres generados por proyecto Compose y puertos de prueba locales | Las automatizaciones que dependan de container_name fijo deberán usar el nombre del servicio |
| Actualizar el mock OFF de pruebas al endpoint actual /search?q= y hits | El helper de pruebas deja de imitar la API antigua; el cliente de producción conserva su contrato |
| Tratar JSON malformado de caché como regresión de disponibilidad y corregirlo | Se mantienen handlers y pruebas de un escenario poco frecuente |
| Admitir aliases de alimentos como objetos/null porque el cálculo los ignora | Menor validación de metadatos sin uso nutricional |
| Conservar la posible reestimación posterior al reconocimiento manual | Permanece la limitación de hash/datos manuales del original |
| Conservar ml=g, ceros LLM a null, nutrientes faltantes y ausencia de reintentos de escritura | Permanecen aproximaciones nutricionales y límites de recuperación existentes |
| Excluir jobs durables, historial persistente, distribución y nuevas funcionalidades de seguridad | El trabajo y estado en memoria siguen perdiéndose al reiniciar |
| Usar transacciones SQLite, según la diferencia técnica aprobada | El momento de persistencia difiere de la exportación diferida de sql.js |
| No atribuir equivalencia exhaustiva a metadatos no caracterizados ni Unicode/configuración patológicos | Un caso futuro no cubierto puede necesitar su propia captura y ajuste |
| Distinguir Docker local de proveedor LLM real, CI remoto y publicación | No se descartan fallos específicos de esos entornos sin probarlos |
| Actualizar el estado actual y conservar las entradas históricas fechadas | Los recuentos históricos no deben confundirse con la tabla final del documento 06 |
| No mostrar un menú de merge/PR para una carpeta sin Git ni publicación solicitada | No se crea repositorio, rama, commit o PR; se conserva el trabajo local |

## Límites aceptados y comprobaciones pendientes

- Se mantienen las limitaciones de producto exigidas por el usuario y descritas en el documento 03.
- La cobertura comprueba los casos documentados; no acredita todos los valores inválidos posibles de cada campo.
- Proveedor LLM real: sin ejecutar, pendiente de la configuración elegida y autorización correspondiente.
- CircleCI: configuración escrita, sin ejecución remota observada.
- Registro de imágenes y despliegue: sin publicación ni sustitución del servicio del usuario.
- No quedan hallazgos menores conocidos aplazados de la revisión.
