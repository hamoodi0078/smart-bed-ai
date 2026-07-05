"""merge_heads

Revision ID: 084855be2828
Revises: d4e5f6a7b8c9, e5f6a7b8c9d0, f7a8b9c0d1e2
Create Date: 2026-07-05 16:53:43.559519
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '084855be2828'
down_revision: Union[str, None] = ('d4e5f6a7b8c9', 'e5f6a7b8c9d0', 'f7a8b9c0d1e2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
