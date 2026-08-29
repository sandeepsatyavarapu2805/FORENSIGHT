import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.contracts import ParserAdapter, ParserDiagnostic, ParserFatalError
from app.ingestion.storage import LocalFileStorage
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.processing_job import ProcessingJob

REFERENCE_PREFIXES = {
    "message": "MSG",
    "call": "CALL",
    "contact": "CONTACT",
    "document": "DOC",
    "media": "MEDIA",
    "location": "LOC",
    "application": "APP",
    "device": "DEVICE",
}


def _set_stage(db: Session, source: EvidenceSource, job: ProcessingJob, stage: str) -> None:
    source.processing_stage = stage
    job.stage = stage
    job.stage_history = [*job.stage_history, stage]
    db.commit()


def _evidence_reference(artifact_type: str) -> str:
    prefix = REFERENCE_PREFIXES.get(artifact_type.lower(), "EVID")
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def process_source(
    db: Session,
    source: EvidenceSource,
    adapter: ParserAdapter,
    storage: LocalFileStorage,
) -> ProcessingJob:
    if not source.storage_key:
        raise ValueError("Source has no validated upload")

    now = datetime.now(UTC)
    source.processing_state = "processing"
    source.processing_stage = "parsing"
    source.error_summary = None
    job = ProcessingJob(
        source_id=source.id,
        status="processing",
        stage="parsing",
        started_at=now,
        stage_history=["parsing"],
    )
    db.add(job)
    db.commit()
    job_id = job.id
    source_id = source.id

    try:
        result = adapter.parse(storage.path_for(source.storage_key))
        diagnostics = list(result.diagnostics)
        _set_stage(db, source, job, "normalization")

        normalized = []
        seen_record_ids: set[str] = set()
        for artifact in result.artifacts:
            artifact_type = artifact.artifact_type.strip().lower()
            original_record_id = artifact.original_record_id.strip()
            if not artifact_type or not original_record_id:
                diagnostics.append(
                    ParserDiagnostic(
                        severity="error",
                        code="invalid_artifact_identity",
                        message="Artifact type and original record identifier are required",
                        original_reference=artifact.original_record_id or None,
                    )
                )
                continue
            if original_record_id in seen_record_ids:
                diagnostics.append(
                    ParserDiagnostic(
                        severity="error",
                        code="duplicate_original_record",
                        message="Duplicate source record was skipped",
                        original_reference=original_record_id,
                    )
                )
                continue
            seen_record_ids.add(original_record_id)
            normalized.append(
                EvidenceItem(
                    evidence_reference=_evidence_reference(artifact_type),
                    case_id=source.case_id,
                    source_id=source.id,
                    artifact_type=artifact_type,
                    original_record_id=original_record_id,
                    occurred_at=artifact.occurred_at,
                    application=artifact.application,
                    searchable_text=artifact.searchable_text,
                    data=artifact.data,
                    raw_metadata=artifact.raw_metadata,
                    parser_identifier=adapter.identifier,
                    parser_version=adapter.version,
                )
            )

        _set_stage(db, source, job, "evidence_organization")
        _set_stage(db, source, job, "indexing")
        for start in range(0, len(normalized), 500):
            db.add_all(normalized[start : start + 500])
            db.flush()

        counts = Counter(item.artifact_type for item in normalized)
        partial = any(item.severity.lower() == "error" for item in diagnostics)
        completed_at = datetime.now(UTC)
        source.evidence_count = len(normalized)
        source.evidence_counts = dict(counts)
        source.is_partial = partial
        source.processing_state = "partially_processed" if partial else "ready"
        source.processing_stage = None
        source.error_summary = (
            "Source partially parsed — continue with caution." if partial else None
        )
        job.status = source.processing_state
        job.stage = None
        job.progress = 100
        job.diagnostics = [item.as_dict() for item in diagnostics]
        job.completed_at = completed_at
        db.commit()
        db.refresh(job)
        return job
    except ParserFatalError as exc:
        error = str(exc)[:500] or "Parser reported a fatal format error"
    except Exception:
        error = "Source processing failed unexpectedly"

    db.rollback()
    failed_source = db.get(EvidenceSource, source_id)
    failed_job = db.get(ProcessingJob, job_id)
    if failed_source is None or failed_job is None:
        raise RuntimeError("Processing state could not be recovered")
    failed_source.processing_state = "failed"
    failed_source.processing_stage = None
    failed_source.error_summary = error
    failed_source.is_partial = False
    failed_source.evidence_count = 0
    failed_source.evidence_counts = {}
    failed_job.status = "failed"
    failed_job.stage = None
    failed_job.error_summary = error
    failed_job.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(failed_job)
    return failed_job


def latest_job(db: Session, source_id: uuid.UUID) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.source_id == source_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )
