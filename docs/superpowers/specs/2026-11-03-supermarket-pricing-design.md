# Propuesta: precios y productos de supermercados en Mealie Enricher

Fecha: 2026-11-03.

Estado: diseño de referencia. Tras revisar la propuesta, el usuario ha autorizado
implementar la opción integrada y reutilizar la clave OpenAI existente. El plan
es [2026-11-03-supermarket-pricing.md](../plans/2026-11-03-supermarket-pricing.md).
La implementación local no autoriza desplegar el servicio del usuario ni publicar
una versión. Las decisiones iniciales de esta conversación se conservan debajo.

## 1. Objetivo

Enriquecer las recetas de Mealie con el coste por ración y los productos que
convendría comprar en cada supermercado configurado. Distinguir cuánto valen los
ingredientes utilizados de cuánto cuesta adquirir los envases completos.

Empezar por Mercadona, con su catálogo consultable en un DuckDB local, y preparar
la incorporación posterior de otros supermercados. Cada supermercado tendrá su
propia selección de productos, cálculo, etiquetas y desglose en los extras.

## 2. Requisitos acordados

| Tema | Decisión |
|---|---|
| Integración | Incorporar la funcionalidad a Mealie Enricher. |
| Primer supermercado | Mercadona. |
| Zona inicial de Mercadona | Código postal `27004`, modificable desde la configuración del proyecto. |
| Origen de los datos | Consultar directamente la API utilizada por la tienda online de Mercadona. |
| Catálogo | Descargar los productos y conservar los datos en DuckDB para consultar en local. |
| Separación de catálogos | Mantener el DuckDB de supermercados separado de BEDCA. |
| Actualización | Una vez por semana por defecto, con frecuencia configurable. |
| Actualización manual | Poder solicitarla en cualquier momento. |
| Selección ambigua | OpenAI Decisions elige entre los productos candidatos. |
| Criterio | Priorizar el encaje con la receta y, entre equivalentes, la relación calidad-precio y la composición saludable. |
| Reevaluación | Volver a comparar cuando cambien precios u opciones relevantes. |
| Costes | Mostrar coste por ración, coste total consumido y compra de envases completos. |
| Etiquetas | Dos etiquetas de importe exacto por supermercado: por ración y compra. |
| Extras | Incluir los tres costes y los productos que se deberían comprar en cada supermercado. |
| Fase actual | Implementación local autorizada; evidencia y límites en la guía de operación. |

Evolución posterior: el usuario autoriza la implementación y el uso de su clave
existente. El intervalo semanal se concreta inicialmente en 168 horas
configurables, sin inventar un día y hora fijos; se adoptan los detalles de
alcance documentados en la guía de operación, conservando pendientes los datos
que no puedan verificarse.

Los apartados siguientes concretan estos requisitos. Las decisiones de detalle
propuestas por el asistente se identifican como tales y pueden ajustarse.

## 3. Alternativas consideradas y elección

| Alternativa | Ventaja | Coste o limitación |
|---|---|---|
| Integrar en Mealie Enricher | Reutilizar su conexión con Mealie, catálogos, Decisions y operación. | Añadir responsabilidades de sincronización y valoración al servicio. |
| Servicio de catálogos independiente | Compartir el catálogo con otros consumidores. | Mantener otro servicio, su configuración y su comunicación con el enriquecedor. |

Se ha elegido la **opción integrada** porque el objetivo inmediato es enriquecer
las recetas del Mealie ya conectado. La integración conservará responsabilidades
internas separadas; no requiere un nuevo servicio de catálogos para el usuario.

## 4. Punto de partida del repositorio

Revisión estática del checkout durante esta conversación, sin validación de una
versión publicada ni de una descarga completa de Mercadona:

- `src/mealie_enricher/catalog/schema.py` ya prepara `retailers`, `stores`,
  `products`, `packages`, `product_nutrients` y `price_observations`.
- `src/mealie_enricher/catalog/store.py` consulta el catálogo existente mediante
  una conexión DuckDB de solo lectura. No es todavía un buscador de productos de
  supermercado con precios.
- `src/mealie_enricher/agents/catalog_decisions.py` ya selecciona un identificador
  entre candidatos de alimentos, permite abstención y valida la respuesta. Habría
  que adaptar el contexto y la política para productos comerciales.
- `src/mealie_enricher/clients/mealie.py` permite leer recetas, crear o recuperar
  etiquetas y enviar un patch de etiquetas y extras.
- `src/mealie_enricher/services/processing.py` puede omitir recetas cuyo hash de
  ingredientes no haya cambiado. El precio necesitará su propia invalidación.
- El checkout contiene otros cambios en curso, incluidos persistencia e historial.
  Esta propuesta no los modifica ni da por publicada su funcionalidad.

La preparación de tablas no equivale a tener un importador de Mercadona, una
sincronización periódica o un cálculo de costes implementados.

## 5. Catálogo local y procedencia

### 5.1 Alcance de la descarga

Se buscará importar el catálogo online accesible para la zona configurada. No se
promete cubrir todos los productos de todas las tiendas físicas: Mercadona
documenta diferencias de disponibilidad en frescos y referencias locales.

Se ha elegido el código postal **27004** como valor inicial para Mercadona.
El código postal estará en la configuración del proyecto y podrá modificarse
sin cambiar código; no será una zona fija dentro del importador. El nombre exacto
del parámetro se definirá al preparar la implementación.

Cada precio conservará su ámbito, fecha y procedencia para evitar mezclar
catálogos o precios de zonas distintas. Cambiar el código postal exigirá obtener
y validar el catálogo del nuevo ámbito antes de usarlo para valorar recetas;
los precios del ámbito anterior no se presentarán como propios del nuevo.
La disponibilidad y la cobertura real de la fuente para `27004` todavía deben
verificarse. Elegir ese valor inicial no acredita que ya se haya comprobado.

La vía elegida es consultar directamente la API utilizada por la tienda online
de Mercadona y transformar sus respuestas en el catálogo local DuckDB. La
referencia revisada usa `https://tienda.mercadona.es/api`, recorre categorías y
obtiene el detalle de los productos. También documenta endpoints para resolver
el código postal y el almacén asociado. Son observaciones de terceros sobre la
API de la tienda, no un contrato oficial de integración verificado por nosotros.

El proyecto `datania/mercadona-catalog` y su documento `api.md` son referencias
técnicas; no se ha decidido incorporarlos como dependencia ni utilizar sus
exportaciones como fuente principal. Deben verificarse el acceso y el ámbito
real de `27004`, las condiciones aplicables, los campos y el recorrido de
categorías antes de implementar. El script revisado no configura por sí mismo
el código postal, por lo que no acredita la cobertura de esa zona.
En esta conversación no se ha realizado una descarga completa.

### 5.2 Datos que conservar

Propuesta de información del catálogo:

- Supermercado, zona o tienda de referencia y versión de la importación.
- Identificador original del producto, nombre, marca, categorías y enlace.
- Presentación: contenido, unidad, número de unidades y pesos neto/escurrido
  cuando estén disponibles y sean relevantes.
- Precio del envase, precio por unidad de medida, moneda, disponibilidad,
  fecha de observación y condiciones de ofertas, si las hay.
- Ingredientes, información nutricional y atributos verificables que aporte la
  fuente. La ausencia de un dato se conserva como ausencia.
- Registro original para revisar errores del importador sin inventar información.

Los nutrientes de un producto comercial no se heredarán automáticamente de un
alimento genérico BEDCA. Se conservará el vínculo con la fuente propia.

Las búsquedas, los filtros, las conversiones conocidas y los cálculos monetarios
se resolverán localmente. Las nuevas decisiones con OpenAI requerirán conexión y
enviarán el contexto necesario y los candidatos; tener DuckDB local no convierte
esa inferencia en una operación sin Internet.

### 5.3 Persistencia y actualización del archivo

Propuesta técnica: un catálogo de supermercados persistente fuera de la imagen,
en un volumen o directorio de datos, con versiones identificables. BEDCA conserva
su ciclo de vida independiente. Reiniciar o actualizar el contenedor no obliga a
descargar de nuevo los productos.

La importación construirá y validará una versión nueva antes de activarla.
El cambio coordinará el cierre y la reapertura de lectores; no se sobrescribirá
un archivo DuckDB abierto por procesos independientes. Una importación incompleta
no sustituirá el último catálogo correcto.

La configuración de las tareas, sus estados y las decisiones reutilizables
podrán apoyarse en la persistencia ya configurada del servicio. DuckDB seguirá
siendo la fuente local de productos y precios; esta propuesta no introduce otra
tecnología de persistencia ni impone un nuevo despliegue de base de datos.

## 6. Actualizaciones automáticas y manuales

Requisitos: frecuencia semanal inicial, frecuencia modificable y actualización
manual disponible en cualquier momento.

Propuestas operativas del asistente:

1. Mantener una programación persistente por supermercado y zona. El día, la hora
   y la zona horaria serán configurables; no se ha elegido un horario concreto.
2. La actualización manual no desplaza por defecto la siguiente ejecución
   programada. Si se cambia esta regla, debe ser visible en la configuración.
3. Coordinar las solicitudes coincidentes para evitar dos importaciones sobre el
   mismo catálogo. Esto se aplica también si hay varios procesos del servicio.
4. Mostrar última actualización correcta, última tentativa, estado, versión,
   número de productos y próxima ejecución.
5. Registrar incorporaciones, bajas y cambios. Una baja solo se determina tras
   una importación completa y válida, no por una descarga parcial fallida.
6. Conservar el catálogo anterior ante un fallo y hacer visible su antigüedad.
7. Si todavía no hay catálogo válido, dejar los precios pendientes y permitir que
   las funciones existentes del enriquecedor sigan operando.

El recorrido previsto es descargar, validar, activar la versión y después
revisar las valoraciones afectadas. La descarga y la escritura en Mealie tienen
estados diferenciados: completar una no acredita haber completado la otra.

## 7. Selección de productos con OpenAI Decisions

### 7.1 Búsqueda y elección

Primero se consultará DuckDB para obtener candidatos compatibles con cada línea
de ingrediente. Se conservarán el texto y las cantidades originales de la receta;
no se exige transformar previamente todos los ingredientes a gramos.

Cuando existan varias opciones, Decisions recibirá una lista corta con sus
identificadores y datos, junto con el contexto necesario de la receta. Solo
podrá seleccionar un identificador ofrecido o abstenerse. Un único candidato
verificado podría resolverse localmente; este es un detalle propuesto para evitar
llamadas que no aportan una elección.

Se propone reutilizar la configuración de Decisions existente con controles
propios de tiempo, concurrencia, consumo y reutilización de respuestas para esta
funcionalidad. No se envía el catálogo completo para decidir cada ingrediente.

### 7.2 Política de selección acordada

La prioridad es respetar la receta: identidad del ingrediente, variedad relevante,
estado antes de cocinar, preparación y compatibilidad de la presentación.
Por ejemplo, distinguir tomate triturado de tomate frito o garbanzos secos de
garbanzos cocidos antes de comparar precios.

Entre productos equivalentes se buscará un equilibrio entre:

- Composición e información nutricional disponible dentro del mismo tipo de
  producto y su función en la receta.
- Atributos de calidad comprobables en la fuente.
- Precio por kilo, litro o unidad compatible.
- Formato, cantidad que necesita la receta y aprovechamiento del envase.

No se ha elegido una puntuación universal de «saludable», pesos numéricos de esos
criterios ni preferencias médicas o dietéticas personales. Como propuesta inicial,
la política será explícita, versionada y evaluada con ejemplos de productos
equivalentes. Los datos ausentes no justifican inventar composición, sabor,
frescura, certificaciones o ventajas nutricionales. La etiqueta NOVA de la receta
no se usará por sí sola como medida de calidad o salubridad de un producto.

### 7.3 Validación, conservación y revisión

La aplicación validará que el producto existe entre los candidatos, corresponde
al supermercado y ámbito consultados, y que su presentación permite el cálculo
que se pretende publicar. Ante abstención, respuesta inválida, error o confianza
insuficiente, el ingrediente queda pendiente. El umbral se ajustará con ejemplos;
una confianza declarada no es una garantía de acierto.

Se guardarán producto elegido, estado, confianza disponible, versión de la
política y huella de los datos considerados. Decisions `choice` no garantiza una
explicación textual; esta propuesta no depende de obtenerla.

La huella incluirá el contexto relevante de receta, raciones y cantidades,
configuración de selección y candidatos con sus datos y precios. Se revisará la
decisión cuando cambien esas entradas, incluidos nuevos competidores relevantes,
no solamente cuando cambie el producto anteriormente elegido. Si nada relevante
cambia, se reutiliza el resultado.

Posibilidad propuesta, aún no concretada: permitir una corrección manual y
marcarla como preferencia fija, excluida de la sustitución automática hasta que
el usuario la libere o el producto deje de ser utilizable.

## 8. Los tres costes y sus cálculos

Para cada receta y supermercado se calcularán separadamente:

| Importe | Significado |
|---|---|
| Coste total de la receta | Suma del valor proporcional de las cantidades utilizadas. |
| Coste por ración | Coste total consumido dividido entre las raciones válidas. |
| Coste de compra | Suma de los envases completos suficientes para elaborar la receta. |

Para una presentación de contenido conocido y compatible:

```text
coste consumido = cantidad utilizada / contenido del envase × precio del envase
envases necesarios = redondeo hacia arriba(cantidad necesaria / contenido del envase)
coste de compra = envases necesarios × precio del envase
sobrante = envases necesarios × contenido del envase − cantidad necesaria
coste por ración = coste total consumido / número de raciones
```

Las líneas que utilicen el mismo producto y presentación se agruparán antes de
redondear envases. Así no se compra dos veces un paquete suficiente para varias
líneas de una misma receta. La compra conjunta de varias recetas queda fuera de
esta primera propuesta.

Los cálculos serán deterministas, con aritmética decimal y redondeo a dos
decimales al presentar importes en euros. No se deduce que un mililitro equivale
a un gramo ni que una pieza tiene un peso universal. Las conversiones requieren
datos compatibles; se respetan peso neto y escurrido y estados seco/cocido.

Propuestas de alcance para la primera versión:

- Suponer que se parte sin existencias en casa al calcular la compra.
- Incluir el precio de los productos; envío y otros servicios quedarían aparte.
- Aplicar ofertas solo cuando se conocen y se cumplen sus condiciones.
- Tratar pesos variables y presentaciones sin contenido determinable como
  estimaciones explícitas o como pendientes, según los datos disponibles.

La cantidad desconocida, «al gusto» sin medida utilizable o el precio ausente no
se convierten en cero. Si faltan raciones pero se conocen ingredientes y precios,
puede existir un total conocido sin coste por ración. Cada importe conservará su
propio estado de completitud.

## 9. Etiquetas exactas y extras por supermercado

### 9.1 Etiquetas elegidas

El usuario ha elegido importes concretos, en lugar de categorías como «económica».
Formato solicitado, con dos decimales y coma decimal:

```text
Mercadona:1,50 €/ración
Mercadona:10,80 € compra
```

Cada supermercado configurado tendrá su propio par de etiquetas. Las etiquetas
deben corresponder al mismo resultado y versión de datos que el desglose actual.
Su representación son nombres de etiqueta; la negrita usada en la conversación
no se trata como formato Markdown dentro del nombre.

Al cambiar el precio, se retirarán de esa receta las referencias a las etiquetas
anteriores gestionadas por este módulo y se incorporarán las nuevas. Se
conservarán las etiquetas personales y las nutricionales existentes.

Como propuesta técnica, la propiedad se registrará por identificador o slug y
tipo de importe en los metadatos. No se identifican etiquetas propias solo por
empezar con «Mercadona:». Un mismo nombre puede estar compartido por varias
recetas: retirar una asociación no autoriza borrar la etiqueta global.

Los importes exactos producen nombres distintos al cambiar de precio. Se
reutilizarán los nombres ya existentes; una eventual limpieza global de etiquetas
sin uso se trataría como una operación independiente.

### 9.2 Contenido de los extras

Se propone un bloque versionado, bajo una clave propia, con un resultado por
supermercado. El nombre de la clave y su representación concreta se fijarán antes
de implementar. El contenido incluirá:

- Identificador y nombre del supermercado, ámbito o zona y moneda.
- Raciones consideradas, coste por ración, total consumido y compra de envases.
- Estado de cada importe: completo, parcial, desconocido o desactualizado.
- Por ingrediente: texto original, producto elegido, identificador, enlace,
  cantidad requerida, conversión aplicada y coste consumido.
- Compra agrupada por producto: presentación, envases necesarios, precio,
  importe de compra y sobrante calculable.
- Ingredientes pendientes y motivo de la falta de datos.
- Fechas de precios y valoración, versión del catálogo y política de selección.
- Evaluación de Decisions disponible y referencias a las etiquetas gestionadas.

Los extras ajenos se conservarán. Guardar datos estructurados no garantiza que
la interfaz de Mealie los represente como una tabla o tarjetas; la presentación
legible y la compatibilidad con la versión instalada requieren validación.

### 9.3 Ejemplo de resultado

Cifras ficticias tomadas del ejemplo de la conversación, no precios observados:

| Supermercado | Raciones | Coste por ración | Total consumido | Compra de envases |
|---|---:|---:|---:|---:|
| Mercadona | 4 | 1,50 € | 6,00 € | 10,80 € |

La receta recibiría las dos etiquetas anteriores y conservaría en los extras el
desglose que explica esos importes. Otro supermercado tendría sus propios
productos y valores, sin mezclar su cesta con la de Mercadona.

## 10. Coherencia, incidencias y compatibilidad

Propuestas de comportamiento para completar el diseño:

- La valoración tendrá una huella independiente del hash nutricional. Cambiar un
  precio puede actualizar costes y etiquetas aunque no cambien los ingredientes.
- El módulo de precios se activará por configuración y actuará sobre las recetas
  de los hogares habilitados para él. Los filtros nutricionales no se convertirán
  implícitamente en filtros de precio; su alcance se concretará antes de ejecutar.
- Tener calorías manuales no impide valorar la receta ni autoriza cambiarlas.
  La elección comercial no modificará automáticamente la nutrición existente.
- Los cambios de precios no reescribirán ingredientes, instrucciones ni raciones.
- Las escrituras se coordinarán por hogar y receta con el procesamiento existente,
  preservando los extras ajenos y evitando bucles de webhooks y resultados antiguos
  que sobrescriban versiones nuevas. En modo multiproceso hará falta coordinación
  compartida o limitar explícitamente el escritor; la cola actual no lo garantiza.
- Se publicará un resultado coherente por receta y supermercado. Activar un
  catálogo no implica que todas sus recetas hayan sido recalculadas: se distinguirán
  los estados pendientes, correctos y fallidos hasta completar la revisión.
- Una descarga fallida conserva los datos anteriores con sus fechas. Una
  reevaluación fallida conserva el último resultado como histórico identificado,
  sin presentarlo como una selección nueva verificada.
- Los importes incompletos no usarán las etiquetas numéricas de un total completo.
  Se propone omitir el importe afectado y mostrar el estado y los datos parciales
  en extras. El texto de una posible etiqueta de estado queda por definir.
- Los fallos de un supermercado o de Decisions no impedirán la nutrición existente
  ni invalidarán los resultados independientes de otros supermercados.
- La publicación en Mealie se verificará y su resultado se registrará. Un fallo
  después de una escritura requerirá comprobar el estado remoto antes de repetirla.

## 11. Responsabilidades que tocaría una implementación futura

| Parte | Responsabilidad prevista |
|---|---|
| Adaptador Mercadona | Descarga, ámbito de zona, normalización y procedencia. |
| Catálogo de supermercados | Búsqueda local, presentaciones, disponibilidad, precios e histórico. |
| Sincronización | Programación configurable, petición manual, exclusión mutua y activación de versiones. |
| Selector comercial | Candidatos, política de elección con Decisions, abstención y reutilización. |
| Calculadora de costes | Conversiones conocidas, agrupación, redondeos, raciones y sobrantes. |
| Procesamiento de recetas | Invalidación independiente, revisiones de recetas afectadas y estado del resultado. |
| Integración con Mealie | Etiquetas exactas, extras, conservación de campos y comprobación de escritura. |
| Configuración e historial | Supermercados habilitados, zona, frecuencia y trazabilidad de incidencias. |

Es una separación conceptual de responsabilidades. No fija nombres de clases,
endpoints ni una lista de tareas de implementación.

## 12. Fuera de la primera propuesta

- Comprar, pagar o añadir automáticamente productos a un carrito.
- Gestionar despensa e inventario doméstico.
- Optimizar una cesta mezclando supermercados o varias recetas.
- Garantizar stock de una tienda física o un precio futuro en caja.
- Prescribir una dieta o asignar una valoración médica a la receta.
- Descargar imágenes para uso sin conexión: posibilidad comentada, no requisito
  elegido. Puede tratarse aparte si se quiere incluir.
- Sustituir o recalcular la nutrición de la receta según el producto comercial.
- Desplegar un servicio adicional de catálogos o exigir otro proceso manual al
  operador para las actualizaciones habituales.

## 13. Decisiones concretadas al implementar y verificaciones pendientes

1. Acceso y descarga completa verificados para `27004`, almacén `4450`: 4.291
   productos enumerados por la API, guardados y consultados en DuckDB, con
   relectura adicional sin red. La cobertura futura y las condiciones de uso
   de datos siguen siendo verificaciones distintas de esta ejecución.
2. Frecuencia semanal concretada como intervalo de `168` horas configurable.
   Controles con token propio: `/pricing/status`, `/pricing/sync` y
   `/pricing/refresh`. No se ha añadido una pantalla ni fijado un día de semana.
3. Política de selección versionada, umbral y modelo de la configuración
   `DECISIONS_*`, máximo inicial de 12 candidatos y 500 decisiones por lote.
   La validación general de calidad requiere un conjunto representativo de
   ejemplos; una única decisión real correcta no la acredita.
4. Primera versión sin despensa, con envío aparte y cantidades no verificables
   pendientes. No se implementa todavía una preferencia manual fija de producto.
5. Extras en `mealie_enricher_pricing`, con un resultado por supermercado.
   Los nombres exactos y el JSON se han validado en un Mealie aislado; la interfaz
   nativa sigue determinando cómo muestra ese bloque, sin tarjetas nuevas.
6. Se valoran las recetas accesibles mediante los tokens configurados, con
   serialización por receta y un único propietario de precios por directorio.
   La programación y el trabajo pendiente sobreviven a reinicios. Las escrituras
   verifican entradas y conservan los campos actuales de Mealie antes del patch.

La implementación conserva los límites de esta propuesta. La evidencia local,
la importación real completa y la validación con Mealie se registran por
separado; no equivalen a un despliegue ni a una publicación.

## 14. Criterios para validar la funcionalidad cuando se construya

- Importación real y completa para el ámbito configurado, con cobertura y origen
  registrados. Una muestra o una respuesta simulada no acreditan esa descarga.
- Consultas y cálculos locales después de importar y supervivencia del catálogo
  al reinicio del servicio.
- Frecuencia semanal configurable, ejecución manual y exclusión de tareas
  coincidentes, incluida la recuperación después de reiniciar.
- Sustitución segura de versiones; descargas parciales no retiran productos ni
  destruyen el catálogo anterior.
- Decisions selecciona solo candidatos válidos y respeta las distinciones de
  ingrediente; los casos sin evidencia permanecen pendientes.
- Revisión al cambiar precios, composición o candidatos relevantes y reutilización
  cuando no cambian las entradas. Un nuevo producto puede afectar una elección.
- Casos monetarios con envases compartidos entre líneas, unidades incompatibles,
  pesos escurridos, raciones ausentes, ofertas y datos parciales.
- Tres importes diferenciados y dos etiquetas exactas por supermercado; una
  actualización sustituye asociaciones propias y conserva etiquetas compartidas.
- Independencia entre supermercados, hogares y resultado nutricional. Verificar
  escrituras reales en una instalación Mealie aislada antes de afirmar integración.
- Distinguir pruebas simuladas, Decisions real, importación real, integración con
  Mealie y eventual publicación. La guía operativa registra cuáles se han
  ejecutado y sus límites; la publicación sigue pendiente.

## 15. Referencias

- [Catálogos actuales del proyecto](../../11-catalogos-duckdb.md).
- [Referencia de investigación: datania/mercadona-catalog](https://github.com/datania/mercadona-catalog).
- [Endpoints observados por el recopilador, documentación no oficial](https://github.com/datania/mercadona-catalog/blob/main/api.md).
- [Código del recopilador de referencia](https://github.com/datania/mercadona-catalog/blob/main/mercadona.py).
- [OpenAI Decisions: opciones cerradas y confianza](https://developers.openai.com/api/docs/guides/decisions).
- [Mealie: extras de recetas](https://mealie.io/documentation/getting-started/api-usage/#recipe-extras).
- [Mercadona: diferencias entre surtido online y tiendas](https://ayuda.tienda.mercadona.es/hc/es/articles/360000841032--Los-productos-online-son-los-mismos-que-en-las-tiendas).
- [DuckDB: concurrencia y acceso al archivo](https://duckdb.org/docs/2.0/connect/concurrency).

## 16. Alcance de esta entrega documental

La entrega inicial fue exclusivamente esta propuesta. Posteriormente el usuario
ha autorizado la implementación local. La guía de [precios de supermercados](../../20-precios-supermercados.md)
describe su operación, evidencia y límites; los detalles que siguen requiriendo
datos reales se verifican como tales, sin convertir una muestra en una descarga
completa o en una publicación.
