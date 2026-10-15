"""add unqueued send event

Revision ID: 4be973480f10
Revises: 8a1f6c69274e
Create Date: 2026-10-15 15:47:14.374437

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4be973480f10'
down_revision: Union[str, Sequence[str], None] = '8a1f6c69274e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("event_valid", "send_events", type_="check")
    op.create_check_constraint(
        "event_valid", "send_events",
        "event IN ('queued', 'sent', 'failed', 'replied', 'bounced', 'requeued', 'unqueued')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM send_events WHERE event = 'unqueued'")
    op.drop_constraint("event_valid", "send_events", type_="check")
    op.create_check_constraint(
        "event_valid", "send_events", "event IN ('queued', 'sent', 'failed', 'replied', 'bounced', 'requeued')"
    )
