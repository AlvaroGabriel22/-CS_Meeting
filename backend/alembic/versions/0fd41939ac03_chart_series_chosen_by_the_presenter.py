"""chart series chosen by the presenter

Revision ID: 0fd41939ac03
Revises: 30154abbfc42
Create Date: 2026-08-20 23:49:18.466978
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0fd41939ac03'
down_revision = '30154abbfc42'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # existing rows need a value: an empty object means "compose the chart
    # automatically", which is exactly what they did before this column existed
    with op.batch_alter_table("department_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("chart_series", sa.JSON(), nullable=False, server_default="{}")
        )


def downgrade() -> None:
    with op.batch_alter_table("department_settings", schema=None) as batch_op:
        batch_op.drop_column("chart_series")
