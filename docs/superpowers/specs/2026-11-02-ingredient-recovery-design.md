# Recover incomplete ingredients inside the enricher

The user selected and authorized automatic recovery inside the enricher, with
weight estimates when possible and no changes to Mealie's original ingredients.

## Approaches

- Repair ingredients in Mealie through its parser: improves shopping and scaling,
  but changes recipe data and depends on Mealie's foods, units and parser setup.
- Recover an internal estimation view: the selected approach. Preserve the source
  ingredient, recover missing fields from `originalText`, and keep uncertainty
  visible rather than inventing quantities.

## Behavior

- Prefer complete structured ingredients. Recover only incomplete ones, using
  explicit Spanish/English quantities, decimal commas, fractions, units and food
  names. Do not overwrite valid structured fields or guess conflicting values.
- Numeric text without an explicit unit represents a count, not a mass. Infer a
  piece unit only when the text supplies that count. Estimate its weight for the
  specific food, retaining size/preparation context.
- Convert explicit mass deterministically. Recovered volume requires a density
  or food-specific weight estimate; do not assume ml equals g.
- Package units without an explicit net mass, qualitative quantities, ranges,
  conflicting fields and unsupported text remain pending. Never substitute zero.
- Retain positive fractional gram estimates on the new recovery path and isolate
  their cache from the legacy integer estimator. Invalid responses are not cached.
- Resolve nutrition through the existing catalog/OFF/LLM path. Python performs
  scaling and aggregation. Preserve legacy fully structured behavior and API
  contracts; add recovery provenance only for ingredients using the new path.
- Pending recovered ingredients appear in unmatched counts and metadata. Keep
  original `recipeIngredient`, reference IDs, instructions and other fields intact
  in memory and in every Mealie PATCH.
- Include recovery version/source text in the hash only for affected recipes, so
  previously processed incomplete recipes are reconsidered without update loops.

## Scope and validation

Use the existing Python/Pydantic/HTTPX implementation and LLM credentials. No new
dependencies, Mealie ingredient writes, automatic publication or deployment.
Validate the supplied chicken/quinoa ingredient shapes, adversarial/ambiguous
inputs, cache behavior, no ingredient mutations, HTTP processing, hash changes,
legacy parity, Ruff and mypy. Explain Mealie parser prerequisites separately.
