# Ingredient Recovery Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, following TDD.

**Goal:** Estimate incomplete imported ingredients without modifying Mealie's source ingredients.

**Architecture:** A pure recovery helper produces a temporary ingredient view and
provenance. Estimator consumes that view, uses deterministic mass conversions or
the existing LLM for specific unit weights, and includes unresolved items in results.

**Tech Stack:** Existing Python 3.14, Pydantic, HTTPX, pytest and SQLite cache.

**Spec:** `docs/superpowers/specs/2026-11-02-ingredient-recovery-design.md`

## Global constraints

- Preserve source recipe ingredients and all prior OpenAI compatibility changes.
- Keep fully structured legacy inputs, manual protection and HTTP contracts stable.
- Unknown quantities remain pending; no uniform piece weights or ml=g assumption
  on recovered ingredients. Respect package uncertainty and explicit source data.
- No new dependencies, credential writes, publication or production ingredient edits.

## Review focus

- Positive structured fields conflicting with source quantities or food names.
- Decimal/fraction weights, invalid/nonfinite provider output and cache isolation.
- Packaging, qualitative amounts, ranges and unknown units mistaken for foods.
- Original-text changes ignored by hashes or updates causing repeated processing.
- Mealie PATCH accidentally containing recovered source ingredients.

## Task 1: Recover incomplete ingredient views

**Files:** Create `services/ingredient_recovery.py` and `tests/unit/test_ingredient_recovery.py`.

**Interfaces:** `recover_ingredient(MealieIngredient) -> RecoveredIngredient | None`;
`RecoveredIngredient` contains temporary ingredient, provenance and pending reason.

- [x] Write table-driven tests for the supplied Spanish ingredient shapes, English
  counts, fractions, decimals, missing amounts, ranges, packages and conflicts.
- [x] Run tests and observe failure, then implement the pure helper.
- [x] Verify no source mutation and complete-ingredient preservation.

## Task 2: Integrate recovery, weight estimates and provenance

**Files:** Update estimator, LLM estimator/prompts, models and tagging; add integration tests.

**Interfaces:** Add `LlmEstimator.estimate_recovered_grams(quantity, unit_name, food_name)`
with strict positive decimal parsing and a separately versioned cache key.

- [x] Write failing integration tests for recovery through catalog and fallback,
  qualitative/package pending outcomes, explicit mass, fractional weights and cache.
- [x] Integrate temporary views before catalog lookup; preserve ambiguity safeguards.
- [x] Attach recovery metadata to new-path matches and nutrition extras, clearing
  stale recovery metadata when the source is repaired.
- [x] Test versioned original-text-sensitive hashes and HTTP PATCH preservation.

## Task 3: Documentation and verification

**Files:** README, Spanish README and the compatibility documentation as needed.

- [x] Document automatic recovery, required LLM settings, limits and Mealie parser
  prerequisites (food/unit data, selected parser and separate AI provider).
- [x] Run targeted tests, full pytest, Ruff checks/format, mypy and diff checks.
- [x] Obtain one read-only review of the complete change and address real defects.
- [x] Report local/runtime evidence and the remaining deployment boundary.
