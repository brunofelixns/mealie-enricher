# Open Source Release Implementation Plan

> **For agentic workers:** Execute this publication plan in the current session and verify each external result before recording completion.

**Goal:** Publish Mealie Enricher with an English landing README, linked Spanish documentation, a public GHCR image, and descriptive GitHub metadata.

**Architecture:** Preserve application behavior and GPLv3/upstream attribution. Keep the existing development Compose and the independent image-only deployment Compose. Publish locally with Docker Buildx rather than depending on hosted Actions credits.

**Tech Stack:** Markdown, Python 3.14, uv, Docker Buildx, GHCR, GitHub CLI.

**Spec:** The user explicitly requested this release on 2026-11-01: English README, Spanish documentation links, published GHCR image, GitHub description and topics.

## Global Constraints

- Preserve Spanish documentation and existing application behavior.
- Exclude local credentials, caches, and BEDCA data from Git and the base image. The separately documented optional BEDCA variant retains the dataset's own non-commercial terms.
- Preserve existing commits and any unrelated working changes.
- Do not claim registry publication until tags and digests are verified remotely.
- Verify anonymous access separately from authenticated publication.

## Review Focus

- Relative links and images must work in both README languages.
- The image-only Compose must reference the actual published version.
- Runtime image metadata must identify its source and version.
- Public source history must exclude credentials and local datasets.
- Multi-platform publication must distinguish emulated checks from native hardware validation.

## Tasks

- [x] Preserve the Spanish landing README; write the English README and deployment guide, add language navigation and contribution instructions.
- [x] Add OCI image labels and a concrete GHCR image reference to deployment examples; validate Compose, documentation links, code checks and ordinary tests.
- [x] Inspect tracked history for publication exclusions, build and smoke-test the image, then publish version 1.13.0 and latest with a source revision label.
- [x] Publish the prepared source to main, set the repository description/topics and public visibility, and make the GHCR package public.
- [x] Verify remote commit, anonymous repository/package access, image digest/platforms, and a clean image-based deployment; record the observed evidence.

Evidence: [Public release record](../../14-publicacion-open-source.md). Optional build attestations were disabled after the initial registry rejection; publication succeeded with the existing credentials and no additional Actions access grant.
