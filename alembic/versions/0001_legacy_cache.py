"""Recognize or create the original cache without deleting existing data."""

from alembic import op
from mealie_enricher.storage.schema import (
    llm_estimate_cache,
    llm_nutrient_cache,
    nutrient_cache,
    unmatched_foods,
)

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (nutrient_cache, unmatched_foods, llm_estimate_cache, llm_nutrient_cache):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (llm_nutrient_cache, llm_estimate_cache, unmatched_foods, nutrient_cache):
        table.drop(op.get_bind(), checkfirst=True)
