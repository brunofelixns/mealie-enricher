# Imagen Docker con BEDCA preparado

## Solicitud y alcance

El usuario solicita que descargar y arrancar una imagen permita usar BEDCA sin
importación manual y que se conserven también los CSV. Confirma distribución
pública no comercial el 2026-11-01. No se publica una imagen desde este cambio.

## Enfoques

- Copiar los datos al volumen en el primer arranque añade escritura y reglas de
  actualización de datos persistentes.
- Guardarlos dentro de la imagen en una ruta independiente permite lectura
  inmediata y actualizaciones junto a la propia imagen. Es la decisión técnica
  adoptada para satisfacer la solicitud.
- La imagen base continúa disponible para instalaciones con catálogo propio.

## Diseño

Una variante añade `/opt/bedca/catalogos.duckdb`, los tres CSV originales en
`/opt/bedca/source/`, un manifiesto del importador y un aviso con atribución y
condiciones. El mantenedor genera DuckDB durante la construcción de la imagen
desde los CSV; el usuario final no descarga ni importa nada al arrancar.

Los datos se proporcionan con un contexto BuildKit explícito; no se añaden a Git
ni al contexto habitual de la imagen base. Los CSV se copian sin alteración y
la construcción falla ante una exportación inválida. El usuario de ejecución
no puede modificar los datos incluidos. SQLite sigue en su volumen escribible.

La variante activa el catálogo por defecto. Ambos Compose permiten elegir
`CATALOG_DB_PATH`, evitando que el volumen `/app/catalogs` oculte los archivos
incluidos en `/opt/bedca`. Un ejemplo de entorno específico permite utilizar el
Compose de despliegue existente con esta variante. El comportamiento nutricional,
la IA y los contratos HTTP no cambian.

## Condiciones

BEDCA conserva sus condiciones propias, separadas de la licencia del código.
Se identifica AESAN/BEDCA v1.0 (2010), el origen de la exportación y las
restricciones de uso. La autorización indicada por el usuario es para
distribución no comercial; no se presenta el dataset como datos GPL de libre
uso comercial. No se cambia la publicación ni la visibilidad de ningún paquete.

Fuentes comprobadas el 2026-11-01:

- https://www.bedca.net/bdpub/UsoBD.pdf
- https://github.com/TerjeRu/bedca-database/blob/main/LICENSE

## Verificación

Se comprobarán CSV idénticos byte a byte, manifiesto, atribución, permisos,
configuración Compose, arranque sin importación, escritura en Mealie real
aislado y actualización del catálogo al recrear el contenedor con otra imagen.
Después se construirá una variante local con la exportación BEDCA real.
