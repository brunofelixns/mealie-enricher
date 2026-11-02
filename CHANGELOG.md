# Changelog

## [1.0.1](https://github.com/brunofelixns/mealie-enricher/compare/v1.0.0...v1.0.1) (2026-11-02)


### Documentación

* **ci:** record github app activation and automatic checks ([1a57bfb](https://github.com/brunofelixns/mealie-enricher/commit/1a57bfbfa148ab2508724953919a7ff772a1a8b0))


### Operación y CI

* **ci:** gate releases behind protected pull requests ([dbdab01](https://github.com/brunofelixns/mealie-enricher/commit/dbdab01ae8eb7190abe5be88ac98778e01673ef4))
* **ci:** keep release checks compatible with version bumps ([d104e9f](https://github.com/brunofelixns/mealie-enricher/commit/d104e9fd969c61447dc548539afa7f179d1ab645))
* **ci:** label pull requests and group weekly dependency updates ([#11](https://github.com/brunofelixns/mealie-enricher/issues/11)) ([4561566](https://github.com/brunofelixns/mealie-enricher/commit/456156644d196930d7a72713dfcd884eb32e6cca))
* **ci:** repair scanner permissions and isolate tag validation ([#10](https://github.com/brunofelixns/mealie-enricher/issues/10)) ([6dd2b05](https://github.com/brunofelixns/mealie-enricher/commit/6dd2b057a40f40acd5ee78cf9f26b6d32c825d7b))
* **ci:** strengthen workflow and release verification ([#6](https://github.com/brunofelixns/mealie-enricher/issues/6)) ([83b20e6](https://github.com/brunofelixns/mealie-enricher/commit/83b20e651175fa8d6bb1c9e5aa60ca7a2705dee9))
* **ci:** use scoped github app for automatic release pr checks ([4161077](https://github.com/brunofelixns/mealie-enricher/commit/4161077379282d790eb337c18445e0145dd57676))
* **container:** resolve image CVEs with a shared Python 3.14 base ([bb718d2](https://github.com/brunofelixns/mealie-enricher/commit/bb718d21a73f33be56f8be258469af20307133b3))


### Mantenimiento

* **deps:** update weekly dependencies ([b636532](https://github.com/brunofelixns/mealie-enricher/commit/b63653229c019f0959dc494fcdbb11469f85914d))

## [1.0.0](https://github.com/brunofelixns/mealie-enricher/releases/tag/v1.0.0) (2026-11-02)

- Primera versión propia con aplicación Python, catálogos DuckDB y variante
  Docker con BEDCA y sus CSV originales.
- CI completo y publicación de imágenes base/BEDCA para amd64 y arm64.

La numeración histórica 1.13.0 se conserva como artefacto anterior independiente.
