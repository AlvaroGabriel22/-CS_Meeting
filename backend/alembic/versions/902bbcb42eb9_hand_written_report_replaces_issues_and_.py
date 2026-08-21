"""hand written report replaces issues and workbook prose

The report of a presentation is written by hand in the application (ADR-0036).
That makes three earlier shapes obsolete at once:

* ``report_blocks`` — prose read out of the workbook (ADR-0034, superseded);
* ``issues`` / ``issue_media`` — the Sprint 5 issue report;
* ``issue_report*`` and ``asset_usages`` — the Sprint 0 grid that was never
  used, and the usage table that pointed at its cells.

Dropped in dependency order: SQLite refuses to drop a table another one still
references.

Revision ID: 902bbcb42eb9
Revises: 5af291c4e799
Create Date: 2026-08-20 18:44:47.754962
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = '902bbcb42eb9'
down_revision = '5af291c4e799'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "version_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("translation_key", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["presentation_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", name="uq_version_report"),
    )
    op.create_index("ix_version_reports_translation_key", "version_reports", ["translation_key"])
    op.create_index("ix_version_reports_version_id", "version_reports", ["version_id"])

    op.create_table(
        "report_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("caption", sa.String(length=300), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["version_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_media_report_id", "report_media", ["report_id"])

    # children first, then their parents
    for table in (
        "asset_usages",
        "issue_media",
        "issues",
        "issue_report_cells",
        "issue_report_columns",
        "issue_report_rows",
        "issue_reports",
        "report_blocks",
    ):
        op.drop_table(table)


def downgrade() -> None:
    """Not reversible.

    The dropped tables held content this product no longer has a place for;
    recreating them empty would be a lie.  Restore from a backup instead.
    """
    raise NotImplementedError("irreversible: restore from a backup")
