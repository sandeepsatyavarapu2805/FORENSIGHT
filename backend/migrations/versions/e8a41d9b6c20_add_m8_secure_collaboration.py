"""add M8 secure collaboration

Revision ID: e8a41d9b6c20
Revises: c3f4a9127e6b
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8a41d9b6c20"
down_revision: Union[str, Sequence[str], None] = "c3f4a9127e6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("case_kind", sa.String(30), server_default="original", nullable=False))
    op.add_column("cases", sa.Column("parent_case_id", sa.UUID(), nullable=True))
    op.add_column("cases", sa.Column("evidence_case_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_cases_parent_case_id", "cases", "cases", ["parent_case_id"], ["id"])
    op.create_foreign_key("fk_cases_evidence_case_id", "cases", "cases", ["evidence_case_id"], ["id"])
    op.create_index(op.f("ix_cases_parent_case_id"), "cases", ["parent_case_id"])
    op.create_index(op.f("ix_cases_evidence_case_id"), "cases", ["evidence_case_id"])

    op.create_table(
        "case_access_grants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("case_id", "owner_id", "recipient_id", "expires_at"):
        op.create_index(op.f(f"ix_case_access_grants_{column}"), "case_access_grants", [column])
    op.add_column("cases", sa.Column("source_grant_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_cases_source_grant_id", "cases", "case_access_grants", ["source_grant_id"], ["id"])
    op.create_unique_constraint("uq_cases_source_grant_id", "cases", ["source_grant_id"])
    op.add_column("auth_sessions", sa.Column("reauthenticated_until", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("case_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "case_id", "action", "occurred_at"):
        op.create_index(op.f(f"ix_audit_events_{column}"), "audit_events", [column])

    op.create_table(
        "proposed_findings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_copy_case_id", sa.UUID(), nullable=False),
        sa.Column("original_case_id", sa.UUID(), nullable=False),
        sa.Column("submitted_by_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column("accepted_finding_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["accepted_finding_id"], ["findings.id"]),
        sa.ForeignKeyConstraint(["original_case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_copy_case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("source_copy_case_id", "original_case_id", "submitted_by_id", "status"):
        op.create_index(op.f(f"ix_proposed_findings_{column}"), "proposed_findings", [column])
    op.create_table(
        "proposed_finding_evidence",
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposed_findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("proposal_id", "evidence_id"),
    )
    op.add_column("findings", sa.Column("origin_proposal_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_findings_origin_proposal_id", "findings", "proposed_findings", ["origin_proposal_id"], ["id"])
    op.create_unique_constraint("uq_findings_origin_proposal_id", "findings", ["origin_proposal_id"])


def downgrade() -> None:
    op.drop_constraint("uq_findings_origin_proposal_id", "findings", type_="unique")
    op.drop_constraint("fk_findings_origin_proposal_id", "findings", type_="foreignkey")
    op.drop_column("findings", "origin_proposal_id")
    op.drop_table("proposed_finding_evidence")
    for column in ("status", "submitted_by_id", "original_case_id", "source_copy_case_id"):
        op.drop_index(op.f(f"ix_proposed_findings_{column}"), table_name="proposed_findings")
    op.drop_table("proposed_findings")
    for column in ("occurred_at", "action", "case_id", "user_id"):
        op.drop_index(op.f(f"ix_audit_events_{column}"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_column("auth_sessions", "reauthenticated_until")
    op.drop_constraint("uq_cases_source_grant_id", "cases", type_="unique")
    op.drop_constraint("fk_cases_source_grant_id", "cases", type_="foreignkey")
    op.drop_column("cases", "source_grant_id")
    for column in ("expires_at", "recipient_id", "owner_id", "case_id"):
        op.drop_index(op.f(f"ix_case_access_grants_{column}"), table_name="case_access_grants")
    op.drop_table("case_access_grants")
    op.drop_index(op.f("ix_cases_evidence_case_id"), table_name="cases")
    op.drop_index(op.f("ix_cases_parent_case_id"), table_name="cases")
    op.drop_constraint("fk_cases_evidence_case_id", "cases", type_="foreignkey")
    op.drop_constraint("fk_cases_parent_case_id", "cases", type_="foreignkey")
    op.drop_column("cases", "evidence_case_id")
    op.drop_column("cases", "parent_case_id")
    op.drop_column("cases", "case_kind")
