# One complete published image

The user requests one image containing the application, BEDCA DuckDB, original
CSVs and attribution, available through `latest` without choosing a variant.
This directly selects the packaging approach and authorizes implementation.

## Approach

Make the root Dockerfile's final stage the complete image. Its existing runtime
stage remains an internal build stage; import the verified BEDCA named context
in another stage and copy only the prepared bundle into the final image.
Build and push one multi-platform candidate, then promote the same digest as
`X.Y.Z` and `latest`. Existing `bedca` and `latest-bedca` aliases can point to
that same image for compatibility; do not create new `X.Y.Z-bedca` variants.
Historical immutable version tags remain unchanged.

Merely redirecting `latest` while building both variants would retain duplicate
publication and security work. Downloading BEDCA at application startup would
add a network dependency and mutable data. Neither meets the requested packaging.

## Contracts

- Default image enables the bundled catalog at `/opt/bedca/catalogos.duckdb`.
- Default deployment Compose and its example environment use that same path.
- Keep read-only catalog data, source CSV byte integrity, NOTICE and user 1000.
- Preserve optional custom catalog mounts and catalog-disabled source operation.
- Preserve amd64/arm64 validation, Trivy, platform SBOMs and signed provenance.
- A new release manifest uses `image_digest`; old dual-image manifests remain
  readable by trusted security tools for historical publication retries.
- Version conflicts block alias writes; repairing an old release never moves
  stable aliases. Never rewrite 1.1.0 to change its contents.
- Ship as 1.2.0 through the existing protected PR/Release Please workflow.

## Verification

Test one candidate build, one digest across current aliases, immutable collisions,
partial retries, legacy manifests, scans and provenance for two platforms.
Test default Compose startup without a deployment-time import or catalog path
override, original CSV preservation and rejection of invalid input. Run the full
suite and existing required GitHub checks, then verify public tags and signatures.
