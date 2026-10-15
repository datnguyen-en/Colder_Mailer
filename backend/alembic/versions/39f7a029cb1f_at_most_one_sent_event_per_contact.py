"""at most one sent event per contact

Revision ID: 39f7a029cb1f
Revises: 4be973480f10
Create Date: 2026-10-15 16:10:30.559206

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39f7a029cb1f'
down_revision: Union[str, Sequence[str], None] = '4be973480f10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Database backstop for "one email per address": a contact can't record two sends.
    op.create_index(
        "uq_send_events_one_sent", "send_events", ["contact_id"], unique=True,
        postgresql_where=sa.text("event = 'sent'"),
    )


def downgrade() -> None:
    op.drop_index("uq_send_events_one_sent", table_name="send_events")
