# Precios y productos de Mercadona

La integración opcional descarga el catálogo online de Mercadona para el código
postal configurado, guarda productos y precios en DuckDB local y valora las
recetas de los hogares conectados. BEDCA y la nutrición existente siguen su
propio flujo. El primer adaptador es Mercadona; otros supermercados necesitarían
su propio adaptador antes de poder habilitarse.

## Activación y configuración

La integración requiere **1.3.0 o posterior** y los archivos Compose y de entorno
de esa versión. La funcionalidad viene desactivada. Configura en tu entorno o archivo `.env`
ignorado los valores siguientes y reinicia el servicio:

```dotenv
PRICING_ENABLED=true
MERCADONA_POSTAL_CODE=27004
PRICING_SYNC_INTERVAL_HOURS=168
PRICING_AUTO_SYNC=true
PRICING_DATA_DIR=/app/data/supermarkets
```

Además, establece `PRICING_ADMIN_TOKEN` con un valor privado aleatorio de al menos
16 caracteres y configura tu clave existente `DECISIONS_API_KEY` o
`OPENAI_API_KEY`. `DECISIONS_API_KEY` tiene prioridad. No utilices la clave de
OpenAI como token de los controles de precios.

No es necesario activar `DECISIONS_ENABLED`, `CATALOG_ENABLED`, `NOVA_ENABLED`
ni el fallback `LLM_ENABLED` para valorar precios. Se reutilizan `DECISIONS_MODEL`,
`DECISIONS_MIN_CONFIDENCE`, `DECISIONS_TIMEOUT_SECONDS` y
`DECISIONS_MAX_CONCURRENCY`. La selección comercial hace llamadas a OpenAI; las
búsquedas y los cálculos consultan datos locales.

En ejecución desde fuentes, utiliza una ruta local como `data/supermarkets`.
Los dos Compose conservan `/app/data` en un volumen persistente. No se escriben
los precios en el DuckDB BEDCA incluido en la imagen.

| Parámetro | Valor inicial | Comportamiento |
|---|---:|---|
| `MERCADONA_POSTAL_CODE` | `27004` | Cinco dígitos, modificable en configuración. |
| `PRICING_SYNC_INTERVAL_HOURS` | `168` | Intervalo positivo y finito entre actualizaciones programadas. |
| `PRICING_AUTO_SYNC` | `true` | Actualizar al arrancar por primera vez y mantener la programación. |
| `PRICING_REQUEST_DELAY_SECONDS` | `2` | Pausa entre peticiones al catálogo. |
| `PRICING_MAX_PRODUCTS` | `10000` | Superarlo rechaza una importación incompleta; no recorta el catálogo. |
| `PRICING_MAX_CANDIDATES` | `12` | Entre 2 y 99; si la búsqueda es demasiado amplia, queda pendiente. |
| `PRICING_MAX_DECISIONS_PER_RUN` | `500` | Límite de nuevas decisiones durante una revisión de recetas. |

El intervalo de 168 horas concreta la frecuencia semanal sin fijar un día y
hora que no se habían elegido. La siguiente ejecución se conserva al reiniciar;
una actualización manual no desplaza esa fecha. Cambiar el intervalo lo
reprograma desde el nuevo arranque. Cambiar el código postal inicia otro ámbito
y exige adquirir sus datos.

## Actualización y controles manuales

Los controles HTTP requieren `Authorization: Bearer <PRICING_ADMIN_TOKEN>` y
rechazan peticiones con cabecera `Origin`. No heredan el CORS abierto de las
rutas heredadas. Usa un cliente HTTP de confianza o PowerShell, con el token
guardado en una variable de entorno, sin imprimirlo:

```powershell
$pricingHeaders = @{ Authorization = 'Bearer ' + $env:PRICING_ADMIN_TOKEN }
Invoke-RestMethod -Uri 'http://localhost:8000/pricing/status' -Headers $pricingHeaders
Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/pricing/sync' -Headers $pricingHeaders
```

- `GET /pricing/status`: ámbito, estado, fechas de intento y éxito, próxima
  ejecución, versión, productos y resultado de la última revisión de recetas.
- `POST /pricing/sync`: solicitar una descarga completa y después revisar costes.
  Devuelve `202 accepted` o `202 running` si ya hay una operación activa.
- `POST /pricing/refresh`: revisar recetas usando el catálogo local sin volver a
  descargarlo. Añadir `?force=true` fuerza nuevas decisiones en los casos que
  requieren el selector, dentro del presupuesto configurado.

El `202` confirma la solicitud, no la terminación. Consulta el estado posterior.
`PRICING_AUTO_SYNC=false` permite operar únicamente mediante estos controles.

Cada adquisición utiliza una sesión aislada, resuelve el código postal y fija
su almacén en las consultas de categorías y productos. Las respuestas inválidas,
un cambio inesperado de ámbito o los fallos de detalle impiden activar un
catálogo parcial. Los reintentos de lectura son limitados.

El catálogo nuevo se publica como un archivo DuckDB inmutable y un manifiesto
atómico; las versiones anteriores conservan observaciones fechadas. Los lectores
abren y cierran cada consulta y no se sobrescribe un archivo abierto. Un bloqueo
de proceso exige un único propietario de precios por directorio de datos: usa
un solo proceso activo con esta función en ese directorio. No es un bloqueo
distribuido para un volumen de red entre distintos sistemas operativos.

## Selección de productos

La búsqueda normaliza nombres y consulta tokens en DuckDB. Una coincidencia
única de nombre exacto se resuelve localmente; las demás listas admisibles se
envían a Decisions con el contexto de la receta, los precios, las presentaciones
y la composición disponible. El selector solo puede devolver un ID ofrecido o
abstenerse. Primero respeta el ingrediente y su preparación; entre equivalentes
valora composición, información nutricional disponible, calidad verificable,
precio comparable y aprovechamiento del envase.

Los precios y cantidades no los genera el modelo. No se inventa una puntuación
de salud ni se infieren nutrientes ausentes. La API puede aportar ingredientes
y alérgenos sin una tabla nutricional numérica. Una etiqueta NOVA de receta no se
utiliza como valoración automática del producto.

Las decisiones se reutilizan con una huella del contexto, la política y los
candidatos con sus precios y composición. Un nuevo competidor o un precio
cambiado puede invalidarlas; cambiar solo metadatos de descarga no las invalida.
Las abstenciones y respuestas no aceptables se conservan para evitar bucles de
llamadas; se revisan al cambiar sus entradas o al pedir una revisión forzada.
Los fallos de conexión, timeout, HTTP 429 y 5xx no se guardan como abstenciones:
dejan la revisión pendiente. Agotar el presupuesto también conserva el trabajo
pendiente para otro lote. La programación vuelve a intentar esas revisiones
después de cinco minutos cuando está habilitada la operación automática.

## Costes, etiquetas y extras

Se distinguen tres importes:

1. Coste total consumido: valor proporcional de las cantidades de la receta.
2. Coste por ración: total consumido dividido entre las raciones conocidas.
3. Compra: suma de los envases completos suficientes, suponiendo que no hay
   existencias en casa. No incluye entrega ni otros servicios.

Se agrupan las líneas que usan el mismo producto y presentación antes de
redondear envases. Los cálculos monetarios utilizan valores exactos y redondeo
decimal al presentar. Las unidades de masa, volumen y piezas permanecen
separadas; no se transforma un litro en un kilo ni se adivina el peso de un huevo.

Ejemplo ficticio para cuatro raciones: total consumido `6,00 €`, coste por ración
`1,50 €` y compra `10,80 €`. Se aplican las etiquetas:

```text
Mercadona:1,50 €/ración
Mercadona:10,80 € compra
```

`extras.mealie_enricher_pricing` contiene un JSON versionado con la clave
`retailers.mercadona`: los tres importes, raciones, importes parciales conocidos,
líneas, compras agrupadas, envases, sobrantes, enlaces, decisiones, pendientes,
fecha, ámbito y versión del catálogo. Las cantidades decimales se guardan como
texto para conservar precisión. La presentación de este JSON en la interfaz
nativa de Mealie depende de esa interfaz; no se ha añadido una nueva pantalla.

Se sustituyen únicamente las asociaciones de etiquetas que este módulo había
registrado como propias. Se conservan las etiquetas personales y los extras
ajenos; no se borran etiquetas globales compartidas. Las etiquetas de importes
distintos pueden acumularse en el organizador global de Mealie.

## Datos pendientes y fallos

Los importes incompletos son `null` y no reciben una etiqueta numérica de total
completo. El subtotal conocido y los motivos permanecen en extras. Sin raciones
puede conocerse el total y la compra, pero no el importe por ración. Los pesos
variables, envases ambiguos y conversiones desconocidas quedan pendientes.

Un fallo de descarga conserva el último catálogo válido y sus fechas. La
activación del catálogo y la revisión de recetas se registran por separado;
`partial` indica fallos de revisión que se pueden reintentar. Una operación
interrumpida se reconoce al reiniciar. Los errores de precios no bloquean el
flujo nutricional y tener calorías manuales no excluye valorar la compra.

La nutrición, los ingredientes y las instrucciones no se sustituyen por los de
un producto seleccionado. Los cambios de precio tienen invalidación propia y
pueden actualizar una receta cuyo hash nutricional siga igual. Las escrituras de
precios se verifican mediante una lectura posterior de la receta.

Los candidatos de una receta se leen con una misma versión de catálogo. Antes
del patch se vuelve a consultar Mealie para conservar cambios personales hechos
durante la selección y diferir la escritura si cambian los ingredientes o las
raciones. Los IDs de referencias e instrucciones que Mealie regenera no se
consideran cambios de contenido. La API no ofrece aquí una escritura condicional
por versión: sigue existiendo una ventana entre la última lectura y el patch.

## Evidencia y límites

La comprobación inicial de acceso reconoció `27004`, devolvió el almacén `4450`
y permitió consultar categorías y un producto. La adquisición usa la API de la
tienda documentada por la comunidad. El catálogo online puede diferir de
una tienda física. Estas pruebas no modificaron la instalación Mealie del usuario.

Validación real adicional del 2026-11-03: el adaptador importó una muestra del
producto `10005` para `27004`, se consultó en DuckDB y Decisions seleccionó ese
ID con confianza `0,96`. Para 200 ml y dos raciones, la muestra produjo `0,49 €`
consumidos, `0,25 €/ración` y `2,45 €` de compra. Es una muestra, no una descarga
completa. Un Mealie Docker aislado también aceptó las etiquetas exactas, los
extras y su sustitución al cambiar precios, conservando las calorías manuales.

La prueba completa posterior del 2026-11-03 descargó los **4.291 productos únicos**
anunciados por las categorías para `27004`, almacén `4450`. Se realizaron 153
consultas de categorías y 4.291 consultas de fichas, sin errores HTTP en la
ejecución completada. La descarga duró 19 min 33 s y la descarga más publicación
y verificación, 20 min 22 s, con pausa de prueba de `0,25` s. El valor predeterminado
del proyecto sigue siendo `2` s.

El archivo DuckDB de prueba ocupa 25.440.256 bytes y conserva 4.291 observaciones
de precio, el ámbito y los datos originales. La relectura comparó todos los campos
de todos los productos. Un proceso nuevo, con las conexiones de red bloqueadas,
volvió a cargarlo y consultó arroz, leche, tomate, garbanzos, aceite de oliva y
salmón. También verificó los acentos, la separación entre códigos postales y la
coincidencia exacta de las columnas decimales con el JSON guardado.

La primera ejecución detectó que la API usa identificadores de variante como
`81649.1`, que el importador rechazaba. Se corrigió su validación conservando el
identificador completo y rechazando rutas o formatos inválidos. El catálogo
completo contiene 54 variantes de este tipo, incluidos panes y pescados.
Las regresiones de adquisición y almacenamiento pasan: `48 passed`.

Hay 3.203 cantidades de envase normalizadas y 2.705 productos con ingredientes.
Los 386 productos de peso variable y las presentaciones ambiguas conservan los
datos originales, con cantidades desconocidas pendientes, sin asignarles pesos
inventados. La descarga completa acredita el surtido enumerado por la API en
esa ejecución; no garantiza la cobertura futura ni el stock de una tienda física.

Los artefactos locales, ignorados por Git, están en
`.cache/mercadona-27004-full/`: `catalog/mercadona-27004.json` apunta al DuckDB,
`latest-report.json` contiene la evidencia de descarga y SQL, y
`offline-report.json` contiene la comprobación sin red. La ejecución fechada
conserva las respuestas de la API para reproducir incidencias.

Prueba conjunta real del 2026-11-04: una receta sintética recorrió el procesamiento
con Mealie y PostgreSQL aislados, los 4.291 productos del catálogo local y
Decisions real. Para 200 ml del producto `10005` y dos raciones, los importes
fueron `0,49 €` consumidos, `0,25 €/ración` y `2,45 €` de compra. Una segunda
ejecución reutilizó las decisiones y NOVA sin llamadas adicionales. Un cambio
de precio simulado en una copia del catálogo produjo `0,52 €`, `0,26 €/ración`
y `2,60 €`, sustituyendo las etiquetas anteriores. Se conservaron las calorías
manuales, la etiqueta personal y los extras, y el historial PostgreSQL sobrevivió
al reinicio. Es una comprobación funcional concreta, no una evaluación general
de la calidad de selección del modelo. Su informe local queda en
`.cache/combined-real-flow/latest-report.json`.

Verificación final del checkout tras la corrección: `757 passed, 37 skipped`; los omitidos son
pruebas optativas, incluida la de precios con Mealie, que se ejecutó aparte y
pasó durante la implementación anterior. Ruff, formato y mypy (60 archivos fuente)
volvieron a pasar. La configuración de los dos Compose pasó durante la implementación.
El Compose de despliegue se validó con las variables de ejemplo
y un override temporal del archivo `.env` del servicio, sin crear un `.env` real.

- [Propuesta y decisiones](superpowers/specs/2026-11-03-supermarket-pricing-design.md).
- [Plan y comprobaciones](superpowers/plans/2026-11-03-supermarket-pricing.md).
- [Referencia de la API observada](https://github.com/datania/mercadona-catalog/blob/main/api.md).
