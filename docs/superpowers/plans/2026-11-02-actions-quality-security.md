# Actions quality and security implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this approved scope task by task.

**Goal:** Apply the Actions improvements approved in this chat to mealie-enricher, including applicable suggestions from mealie-mcp-server.

**Architecture:** Preserve the existing full-suite and immutable-image publication gates. Add independent workflow/code/dependency checks, digest-based image scanning and evidence, and scheduled compatibility checks. Keep PR-based integration and manual release approval.

**Tech Stack:** GitHub Actions, Python 3.14, uv, Release Please, actionlint, zizmor, CodeQL, Trivy and GitHub attestations.

**Spec:** The user's approved review and additional table in this chat.

## Global constraints

- Scope is mealie-enricher; references to mealie-mcp-server are design input only.
- Run full CI for pull_request, push to main and workflow_dispatch without duplicate branch pushes.
- Keep the required full-suite check and reject skipped integration tests.
- Pin third-party actions and scanner images. Scan immutable digests before promotion.
- Never rewrite historical version tags or merge a release PR automatically.
- Use one dependency-update bot; no new permanent credentials.
- Preserve app contracts and BEDCA source integrity and licensing.

## Review focus

- Malformed or incomplete scanner reports must fail closed.
- ARM reports and SBOMs must refer to their own platform digest.
- Retrying publication must recover immutable candidates and evidence without rebuilding or replacing version tags.
- Scheduled checks must not modify the published images or call live LLM providers.
- New checks must work on fork PRs with read-only tokens and without secrets.

## Tasks

- [x] 1. Establish baseline. Add workflow linting, PR-title policy, CodeQL, dependency review and grouped dependency updates. Validate with the real tools and title-policy regression tests.
- [x] 2. Add coverage floor and visible test/coverage summary. Verify malformed reports and threshold boundaries; run full ordinary suite to measure the baseline.
- [x] 3. Add a shared pinned Trivy scanner for both platforms and variants, fail-closed promotion gate, SBOMs, signed provenance and durable release assets. Test reports, platform selection and retries.
- [x] 4. Add weekly digest scans and Mealie stable compatibility checks. Verify digest resolution and isolated image override without publication.
- [x] 5. Document operation and recovery; run lint, types, Python/Node suites, workflow linters and bot config validation. Obtain a fresh whole-branch review, fix actionable findings, open a PR and observe actual checks.

## Decisions and evidence

- The source checkout is clean. Native managed worktree starts at origin/main (4161077), excluding the unrelated open documentation PR #5.
- GitHub App integration is already on main; activation evidence is in PR #5. This change does not reconfigure its credentials.
- User approval of the preceding recommendations authorizes execution; routine implementation choices are resolved inline.
- Baseline: 372 passed, 24 opt-in Docker tests skipped, 144.74s; line coverage 95.5943%. Node: 20 passed.
- Real actionlint and zizmor auditor checks pass. Dependabot configuration passes JSON schema validation.
- Quality/scanner/compatibility policies: 35 tests passed, including malformed report, policy, four-platform coverage, failed retry and release-SHA provenance tests. The malformed vulnerability dictionary regression was observed failing before correction.
- Ruling: use Dependabot, not a second Renovate bot. Its Docker manager owns the canonical Trivy pin; uv updates include indirect dependencies. Full lock regeneration is intentionally not added.
- Ruling: sign explicit SLSA promotion provenance instead of claiming every retry built the images. Source SHA and candidate digests are explicit.
- Real scan of all four public platform images produced reports, CycloneDX and SARIF and correctly blocked on 56 fixable HIGH/CRITICAL findings per platform image. Existing images and aliases were not changed.
- Live issuance of OIDC signatures and durable release assets will occur on the next approved release; no release PR is merged to manufacture a test publication.
- Final review: three actionable findings, all addressed in one pass. Keep generic quality/security/signing tools at the trusted workflow SHA for old-source recovery, inherit the Compose pin unless explicitly overridden, and cover both composite-action directories in Dependabot.
- Recovery and policy regression suite after the fixes: 76 passed. The default-image regression was observed failing before the fix; legacy CLI tests explicitly cover missing helpers in the source checkout and Windows UTF-8.
- Ruling on review's excluded topics: existing public-image CVE remediation remains a separate change; this task enables detection and blocking. Historical images remain unsigned. No minor findings deferred.
- Full final local suite after review fixes: 410 passed, 24 opt-in Docker tests skipped, 95.59% coverage. New checks passed on PR #6 (CodeQL Python/Actions, dependency review, title, actionlint/zizmor); full Docker CI remains the integration gate.
- Test subprocesses and fake scanners write to temporary summary files, so synthetic 96% coverage or clean-image fixtures cannot contaminate the actual Actions summary.
- GitHub review identified the project's existing ci/revert types missing from the title policy. Both were observed failing, added, and covered by a regression parameterized over every Release Please changelog type. No release configuration or increment rule changes.
- PR #6 merged as 83b20e6 after 446 Python tests without omissions, 20 Node tests and 95.65% line coverage. All seven checks are required on strict main; admin protection, PRs and no force-push/deletion remain active.
- Manual Linux scan exposed bind-mount permission denial with dropped capabilities. Follow-up uses the runner UID/GID and explicit non-root cache/HOME paths, with a real Docker filesystem regression added to full CI.
- CodeQL's conservative dynamic-checkout/cache findings prompted an explicit workflow_dispatch guard on tag checkout and disabled shared uv caching in verification. Normal PR/main CI uses its first exact github.sha checkout. This trades a small dependency download for removing the cache-write surface entirely.
- Manual compatibility run 41480075135 passed against official stable Mealie v3.30.0; main push CI 41479855194 also passed. The first manual scanner run failed on Linux mount permissions, not on the vulnerability policy, and is followed up explicitly.
- PR #10 merged as 6dd2b05 after the full CI including the Docker permissions regression. Corrected scan 41482511743 generated four platform reports and SBOMs, uploaded all four SARIF analyses and retained its artifact; it correctly blocked the existing images on 20 distinct fixable CVEs (56 package findings per image).

## User-requested extension: labels and grouped maintenance

- Preserve the already implemented typed TOML updater for uv.lock. Add a real-lock SDK regression proving only the project version changes; keep `uv sync --locked` before subsequent frozen commands. No version-policy or pre-major changes.
- Add trusted-base actions/labeler v7 without a PR checkout, with predefined api/db/tests/docs/ci labels, additive synchronization and optional manual PR number. Validate both workflow and label rules, then exercise on the existing release PR without touching autorelease labels.
- Consolidate all five dependency ecosystems in one native multi-ecosystem weekly group with inherited chore(deps) messages and one open ordinary update PR. Keep security-update handling and human merging.
- Schema and actual zizmor parsing require commit-message on the multi-ecosystem group only; individual update blocks inherit it. No scope-based changelog filtering is introduced; grouping provides one maintenance entry while preserving the existing version policy.
- Independent extension review: no defects in labeler, group configuration or real-lock regression. Actual Dependabot PR #8 exposed an old SDK test coupled to python:3.14.6-slim; compare FROM lines instead and keep automatic Python image updates within supported 3.14.x.
- Five CodeQL pipeline alerts (#1-4, #6) reviewed statically against live main6dd2b05: not actionable with high confidence under the current source-validation chain. Alerts remain open; no queries excluded or findings dismissed. Scope excludes upgrading to Python3.15 or remediating current OS-package CVEs.
