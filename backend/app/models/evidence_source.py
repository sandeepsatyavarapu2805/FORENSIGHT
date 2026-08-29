import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.case import Case


class EvidenceSource(Base):
    __tablename__ = "evidence_sources"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_evidence_sources_storage_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    imported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_evidence_sources_imported_by_id_users"),
        nullable=True,
        index=True,
    )
    imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parser_identifier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    processing_state: Mapped[str] = mapped_column(
        String(40), nullable=False, default="registered", server_default="registered", index=True
    )
    processing_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_partial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    evidence_counts: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    case: Mapped["Case"] = relationship(back_populates="evidence_sources")
