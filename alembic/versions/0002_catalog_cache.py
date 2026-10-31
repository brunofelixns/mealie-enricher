"""Add only a contextual selection cache; catalogs live in DuckDB."""

from alembic import op
from mealie_enricher.storage.schema import catalog_resolution_cache

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    catalog_resolution_cache.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    catalog_resolution_cache.drop(op.get_bind(), checkfirst=True)
