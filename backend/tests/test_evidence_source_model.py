from app.models.case import Case
from app.models.evidence_source import EvidenceSource


def test_evidence_source_model_columns() -> None:
    assert EvidenceSource.__tablename__ == "evidence_sources"
    assert set(EvidenceSource.__table__.columns.keys()) == {
        "id",
        "case_id",
        "label",
        "description",
        "original_filename",
        "storage_key",
        "file_size",
        "sha256",
        "imported_by_id",
        "imported_at",
        "parser_identifier",
        "parser_version",
        "processing_state",
        "processing_stage",
        "is_partial",
        "error_summary",
        "evidence_count",
        "evidence_counts",
        "created_at",
        "updated_at",
    }


def test_case_evidence_source_relationship() -> None:
    assert Case.evidence_sources.property.back_populates == "case"
    assert EvidenceSource.case.property.back_populates == "evidence_sources"
