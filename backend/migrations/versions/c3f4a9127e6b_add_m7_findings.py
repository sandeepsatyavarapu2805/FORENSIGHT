"""add M7 findings

Revision ID: c3f4a9127e6b
Revises: 67fe8ebaf96b
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3f4a9127e6b"
down_revision: Union[str, Sequence[str], None] = "67fe8ebaf96b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_findings_case_id"), "findings", ["case_id"], unique=False)
    op.create_index(op.f("ix_findings_created_by_id"), "findings", ["created_by_id"], unique=False)
    op.create_table(
        "finding_evidence",
        sa.Column("finding_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"]),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("finding_id", "evidence_id"),
    )


def downgrade() -> None:
    op.drop_table("finding_evidence")
    op.drop_index(op.f("ix_findings_created_by_id"), table_name="findings")
    op.drop_index(op.f("ix_findings_case_id"), table_name="findings")
    op.drop_table("findings")
