# Recuperación interna de ingredientes

El enricher puede calcular recetas que conservan el texto del ingrediente en
`originalText`, pero tienen `food`, `unit` o `quantity` incompletos. Construye una
copia interna y nunca envía `recipeIngredient` ni `recipeInstructions` en un PATCH.

## Interpretación

| Texto de origen | Interpretación |
|---|---|
| `100 gramo(s) Quinoa` | 100 g de Quinoa, sin estimar el peso |
| `8 unidad(es) Jamoncitos de pollo` | 8 piezas; peso comestible por pieza estimado para ese alimento |
| `1 berenjena` | Una pieza; peso estimado, conservando tamaño y notas si aparecen |
| `½ cucharada de aceite de oliva` | Media cucharada; conversión por alimento, sin asumir ml=g |
| `2 latas de atún de 80 g` | 160 g de contenido indicado; la preparación y el escurrido siguen siendo contexto relevante |
| `1 sobre de pimentón (4 g)` | 4 g explícitos |
| `1 sobre de pimentón` | Pendiente: falta el peso del envase |
| `sal al gusto` o `1-2 tomates` | Pendiente: falta una cantidad concreta |

Se reconocen unidades frecuentes en español e inglés, decimales con coma,
fracciones simples, mixtas y Unicode, y las formas `gramo(s)` / `unidad(es)`.
Los campos estructurados válidos tienen prioridad; cantidades, unidades o alimentos
contradictorios quedan pendientes para evitar combinar datos de ingredientes distintos.
El texto no reconocido se conserva y puede quedar sin resolver.

Los alimentos se resuelven mediante el catálogo y el flujo OFF/LLM existente.
El catálogo ambiguo mantiene su abstención: recuperar el texto no autoriza a
escoger otro alimento ni a ignorar su preparación. Python hace las conversiones
exactas, sumas, división por raciones y redondeo.

## Configuración del enricher

La recuperación de texto y masas explícitas está activa sin un nuevo ajuste.
Para estimar piezas, cucharadas o densidades se requiere el fallback LLM:

```dotenv
LLM_ENABLED=true
LLM_BASE_URL=https://api.openai.com/v1
LLM_ENDPOINT_URL=/chat/completions
LLM_MODEL=gpt-6.1-sol
LLM_MAX_TOKENS_GRAMS=1024
LLM_MAX_TOKENS_NUTRIENTS=2048
```

Configura también `LLM_API_KEY` mediante el mecanismo de secretos de tu despliegue.
`OPENAI_API_KEY` / `DECISIONS_API_KEY` corresponden al selector Decisions y no
activan por sí solos el fallback de pesos. Sin LLM, las masas explícitas siguen
funcionando y los pesos que necesiten estimación permanecen pendientes.

Los pesos recuperados admiten decimales positivos estrictos, usan una caché
versionada separada del estimador entero anterior y no guardan respuestas inválidas.
La interpretación de una cantidad no equivale a un peso medido: los pesos generados
quedan identificados como estimaciones.

## Diagnóstico y recálculo

Los ingredientes pendientes cuentan en `unmatchedCount` y en
`calorie_estimator_unmatched`. El extra `calorie_estimator_ingredient_recovery`
incluye texto original, referencia, campos recuperados, cantidad, unidad, alimento,
estado, motivo y peso estimado cuando exista.

Motivos habituales: `quantity_missing`, `quantity_ambiguous`, `conflicting_quantity`,
`conflicting_unit`, `conflicting_food`, `package_weight_unknown`, `weight_unknown`
y `nutrients_unknown`. Los pendientes no se convierten en cero. Se conserva la
limitación existente de suma parcial: si se resuelve parte de la receta, sus
nutrientes no representan necesariamente el total completo.
Los nutrientes automáticos que pasan a ser desconocidos se retiran, junto con
totales y referencias LLM obsoletos, para no conservar cifras de una versión anterior.

El hash incorpora la versión y el texto de los ingredientes afectados. Un cambio
en `originalText` permite recalcularlos y el PATCH del estimador no crea un bucle.
Si reparas los campos en Mealie, la nueva información tiene prioridad y se retira
la recuperación anterior. Tras desplegar una corrección de proveedor, `POST /estimate`
permite forzar el recálculo aunque el texto no haya cambiado.

## Si falla «Analizar ingredientes» en Mealie

Es un flujo independiente de esta recuperación. Comprueba:

1. Los catálogos de alimentos y unidades del grupo deben contener las entradas
   que quieres enlazar. Si están vacíos, Mealie permite cargarlos en tu idioma;
   repetir la carga puede crear duplicados.
2. Las cantidades de ingredientes deben estar habilitadas en la receta.
3. Selecciona el parser que quieres utilizar. Si el NLP interpreta mal el texto,
   prueba el parser de IA y revisa su resultado antes de guardar.
4. El parser de IA necesita un proveedor predeterminado configurado en Mealie.
   Sus credenciales y modelo son independientes de los `LLM_*` del enricher.
5. Si una comida o unidad no se encuentra, Mealie puede requerir que confirmes su
   creación y guardes el resultado. Su parser no aporta por sí solo el peso de
   una pieza ni el peso neto desconocido de un sobre.

Referencias: [ingredientes estructurados de Mealie](https://mealie.io/documentation/getting-started/faq/#how-do-i-enable-smart-ingredient-handling)
y [proveedores de IA de Mealie](https://mealie.io/documentation/getting-started/installation/ai-providers/).

## Verificación local del cambio (2026-11-02)

- Suite Python actualizada sobre main: 513 pruebas aprobadas, 25 comprobaciones
  optativas omitidas y 95,98 % de cobertura. CI ejecuta también las integraciones
  con Docker, BEDCA y Mealie real antes de permitir la fusión.
- Recuperación y estimación: 65 pruebas específicas, incluidas regresiones de
  envases, cantidades alternativas, contexto de tamaño y retirada de nutrición antigua.
- Ruff, formato, mypy y comprobación de diff aprobados.
- Tres peticiones reales de pesos a `gpt-6.1-sol` devolvieron HTTP 200; se verificó
  una respuesta decimal y que repetir la consulta utilizara la caché. Se empleó
  un transporte HTTPS síncrono de diagnóstico para sortear un fallo de DNS del
  cliente asíncrono en el entorno Windows; no forma parte del código de producción.
- La prueba HTTP local comprueba que los PATCH solo contienen nutrición, etiquetas
  y extras. Esta verificación local no modifica recetas ni despliega el servidor.
