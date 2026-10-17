"""template choice per company and contact

Revision ID: f88f0891c237
Revises: 5ce7cfc38e63
Create Date: 2026-10-17 15:02:40.386381

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f88f0891c237'
down_revision: Union[str, Sequence[str], None] = '5ce7cfc38e63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Which template a company / contact gets; NULL falls back to the company's, then the default.
    for table in ("companies", "contacts"):
        op.add_column(table, sa.Column("template_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"{table}_template_id_fkey", table, "templates",
                              ["template_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    for table in ("contacts", "companies"):
        op.drop_constraint(f"{table}_template_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "template_id")
