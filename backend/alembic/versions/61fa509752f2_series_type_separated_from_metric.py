"""series type separated from metric

Revision ID: 61fa509752f2
Revises: e1147da3d1bd
Create Date: 2026-08-19 21:17:35.693873
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '61fa509752f2'
down_revision = 'e1147da3d1bd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """``series`` becomes ``series_type`` and reaches the rows as well.

    A rename, not a drop: an already imported table keeps the series it had
    (ADR-0012).
    """
    with op.batch_alter_table("table_columns", schema=None) as batch_op:
        batch_op.alter_column(
            "series", new_column_name="series_type", existing_type=sa.String(length=60)
        )

    with op.batch_alter_table("table_rows", schema=None) as batch_op:
        batch_op.add_column(sa.Column("series_type", sa.String(length=60), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("table_rows", schema=None) as batch_op:
        batch_op.drop_column("series_type")

    with op.batch_alter_table("table_columns", schema=None) as batch_op:
        batch_op.alter_column(
            "series_type", new_column_name="series", existing_type=sa.String(length=60)
        )
