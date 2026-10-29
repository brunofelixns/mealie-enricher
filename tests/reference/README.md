# Referencia ejecutable

La captura importa las fuentes originales desde .reference/mealie-calorie-estimator, fijadas en c2dc71a1d8effe29375391f2fe50da94d27cfd7d.

Ejecutar desde la raíz:

~~~powershell
git clone https://github.com/timo-reymann/mealie-calorie-estimator .reference/mealie-calorie-estimator
git -C .reference/mealie-calorie-estimator checkout --detach c2dc71a1d8effe29375391f2fe50da94d27cfd7d
Push-Location .reference/mealie-calorie-estimator
npm.cmd ci
npm.cmd run typecheck
npm.cmd test
Pop-Location
node .reference/mealie-calorie-estimator/node_modules/tsx/dist/cli.mjs tests/reference/capture.mts
~~~

No se editan fuentes upstream. Se usan claves sintéticas, fetch simulado y un servidor Mealie local que solo devuelve datos sintéticos. No se contacta con proveedores reales. El registro de /health se ejecuta a partir del fragmento exacto de src/index.ts, porque ese módulo inicia un servidor y no exporta su aplicación.

Los casos contienen entradas y resultados observados, no resultados recalculados por la futura implementación Python. El manifiesto enumera los contratos cubiertos y los archivos generados. Las capturas se generan con reloj controlado; los UUID se sustituyen de forma estable manteniendo su formato.

Si .reference ya existe, comprobar su commit y omitir clone. Estado final: 125 casos y 127 artefactos; regeneración repetida sin diferencias de hashes. El capturador también registra cuerpos HTTP raw para no convertir automáticamente entradas inválidas en JSON válido.
