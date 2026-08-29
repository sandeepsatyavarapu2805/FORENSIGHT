import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.evidence_item import EvidenceItem
    from app.models.finding import Finding


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    __table_args__ = (PrimaryKeyConstraint("finding_id", "evidence_id"),)

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id"), nullable=False
    )

    finding: Mapped["Finding"] = relationship(back_populates="evidence_links")
    evidence: Mapped["EvidenceItem"] = relationship()
