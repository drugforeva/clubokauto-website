"""Флаг «спасать по ответу» в настройках.

Revision ID: 0002_rescue_replies
Revises: 0001_initial
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_rescue_replies"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default нужен только уже существующим строкам: у новых
    # значение проставляет модель, поэтому сразу его снимаем.
    op.add_column(
        "settings",
        sa.Column(
            "rescue_replies",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    with op.batch_alter_table("settings") as batch:
        batch.alter_column("rescue_replies", server_default=None)


def downgrade() -> None:
    op.drop_column("settings", "rescue_replies")
