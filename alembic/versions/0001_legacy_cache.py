"""Recognize or create the original cache without deleting existing data."""

from alembic import op
from mealie_enricher.storage.schema import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    metadata.drop_all(op.get_bind(), checkfirst=True)
