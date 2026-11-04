"""Persist execution history independently of cache expiry."""

from alembic import op
from mealie_enricher.storage.schema import execution_history

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execution_history.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    execution_history.drop(op.get_bind(), checkfirst=True)
