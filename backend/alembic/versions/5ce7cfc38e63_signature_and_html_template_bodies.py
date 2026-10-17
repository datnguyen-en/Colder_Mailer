"""signature and html template bodies

Revision ID: 5ce7cfc38e63
Revises: 39f7a029cb1f
Create Date: 2026-10-17 14:43:38.358548

"""
import html
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ce7cfc38e63'
down_revision: Union[str, Sequence[str], None] = '39f7a029cb1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Frozen copy of richtext.text_to_html: migrations must not change if app code does.
def _text_to_html(text: str) -> str:
    paragraphs = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    return "".join(
        f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip()
    )


def upgrade() -> None:
    op.add_column("settings", sa.Column("signature", sa.Text(), server_default="", nullable=False))
    # Template bodies become HTML: convert existing plain-text ones to paragraphs.
    conn = op.get_bind()
    for template_id, body in conn.execute(sa.text("SELECT id, body FROM templates")).all():
        if not re.search(r"</?(p|br|ul|ol|li|strong|em|a)\b", body, re.IGNORECASE):
            conn.execute(sa.text("UPDATE templates SET body = :body WHERE id = :id"),
                         {"body": _text_to_html(body), "id": template_id})


def downgrade() -> None:
    # Template bodies stay HTML; the old plain-text sender would send the tags literally,
    # so downgrading also needs the bodies rewritten by hand.
    op.drop_column("settings", "signature")
