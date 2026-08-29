import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint("source_id", "original_record_id", name="uq_evidence_source_record"),
        Index("ix_evidence_case_type", "case_id", "artifact_type"),
        Index("ix_evidence_source_type", "source_id", "artifact_type"),
        Index("ix_evidence_case_timestamp", "case_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evidence_reference: Mapped[str] = mapped_column(
        String(80), unique=True, nullable=False, index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_sources.id"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    original_record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    application: Mapped[str | None] = mapped_column(String(150), nullable=True)
    searchable_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    raw_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    parser_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
