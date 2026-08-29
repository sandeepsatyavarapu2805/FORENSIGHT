import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import require_case_view, require_original_owner
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.ingestion.processor import latest_job, process_source
from app.ingestion.registry import ParserRegistry, get_parser_registry
from app.ingestion.storage import (
    LocalFileStorage,
    UploadTooLargeError,
    get_file_storage,
)
from app.models.case import Case
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.schemas import (
    EvidenceItemResponse,
    ProcessingJobResponse,
    SourceCreate,
    SourceResponse,
    SourceUpdate,
)
from app.config import settings

router = APIRouter(prefix="/cases/{case_id}/sources", tags=["evidence sources"])


def _owned_source(
    db: Session, case_id: uuid.UUID, source_id: uuid.UUID, owner_id: uuid.UUID
) -> EvidenceSource:
    source = db.scalar(
        select(EvidenceSource)
        .join(EvidenceSource.case)
        .where(
            EvidenceSource.id == source_id,
            EvidenceSource.case_id == case_id,
            Case.owner_id == owner_id,
            Case.case_kind == "original",
        )
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


def _view_source(
    db: Session, case_id: uuid.UUID, source_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[EvidenceSource, uuid.UUID]:
    access = require_case_view(db, case_id, user_id)
    source = db.scalar(select(EvidenceSource).where(
        EvidenceSource.id == source_id,
        EvidenceSource.case_id == access.evidence_case_id,
    ))
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source, access.evidence_case_id

@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(
    case_id: uuid.UUID,
    payload: SourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceSource:
    require_original_owner(db, case_id, current_user.id)
    source = EvidenceSource(case_id=case_id, **payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("", response_model=list[SourceResponse])
def list_sources(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EvidenceSource]:
    access = require_case_view(db, case_id, current_user.id)
    return list(
        db.scalars(
            select(EvidenceSource)
            .where(EvidenceSource.case_id == access.evidence_case_id)
            .order_by(EvidenceSource.created_at.desc())
        )
    )


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(
    case_id: uuid.UUID,
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceSource:
    source, _ = _view_source(db, case_id, source_id, current_user.id)
    return source


@router.patch("/{source_id}", response_model=SourceResponse)
def update_source(
    case_id: uuid.UUID,
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceSource:
    source = _owned_source(db, case_id, source_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    db.commit()
    db.refresh(source)
    return source


@router.post(
    "/{source_id}/upload",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source_file(
    case_id: uuid.UUID,
    source_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    registry: ParserRegistry = Depends(get_parser_registry),
    storage: LocalFileStorage = Depends(get_file_storage),
) -> EvidenceSource:
    source = _owned_source(db, case_id, source_id, current_user.id)
    if source.storage_key is not None or source.evidence_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This source already has an accepted upload",
        )

    supplied_name = file.filename or ""
    adapter = registry.for_filename(supplied_name)
    if adapter is None:
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="No parser adapter supports this source format",
        )

    source.processing_state = "uploading"
    source.error_summary = None
    db.commit()
    try:
        stored = await storage.save(file, settings.upload_max_bytes)
    except UploadTooLargeError:
        source.processing_state = "failed"
        source.error_summary = "Source file exceeds the configured size limit"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=source.error_summary,
        ) from None
    except ValueError as exc:
        source.processing_state = "failed"
        source.error_summary = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))

    source.processing_state = "validating"
    db.commit()
    try:
        validation = adapter.validate(stored.path)
    except Exception:
        storage.delete(stored.storage_key)
        source.processing_state = "failed"
        source.error_summary = "Source validation failed unexpectedly"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=source.error_summary,
        ) from None
    if not validation.valid:
        storage.delete(stored.storage_key)
        source.processing_state = "failed"
        source.error_summary = validation.error or "Source validation failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=source.error_summary,
        )

    source.original_filename = stored.original_filename
    source.storage_key = stored.storage_key
    source.file_size = stored.size
    source.sha256 = stored.sha256
    source.imported_by_id = current_user.id
    source.imported_at = datetime.now(UTC)
    source.parser_identifier = adapter.identifier
    source.parser_version = adapter.version
    source.processing_state = "validated"
    source.processing_stage = None
    source.is_partial = False
    source.error_summary = None
    db.commit()
    db.refresh(source)
    return source


@router.post("/{source_id}/process", response_model=ProcessingJobResponse)
def confirm_and_process_source(
    case_id: uuid.UUID,
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    registry: ParserRegistry = Depends(get_parser_registry),
    storage: LocalFileStorage = Depends(get_file_storage),
) -> ProcessingJob:
    source = _owned_source(db, case_id, source_id, current_user.id)
    if source.processing_state != "validated" or not source.original_filename:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source must have a validated upload before processing",
        )
    adapter = registry.for_filename(source.original_filename)
    if adapter is None or adapter.identifier != source.parser_identifier:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The validated parser adapter is unavailable",
        )
    return process_source(db, source, adapter, storage)


@router.get("/{source_id}/processing", response_model=ProcessingJobResponse | None)
def get_processing_status(
    case_id: uuid.UUID,
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProcessingJob | None:
    source, evidence_case_id = _view_source(db, case_id, source_id, current_user.id)
    return latest_job(db, source.id)


@router.get("/{source_id}/evidence", response_model=list[EvidenceItemResponse])
def list_source_evidence(
    case_id: uuid.UUID,
    source_id: uuid.UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EvidenceItem]:
    source, evidence_case_id = _view_source(db, case_id, source_id, current_user.id)
    return list(
        db.scalars(
            select(EvidenceItem)
            .where(
                EvidenceItem.case_id == evidence_case_id,
                EvidenceItem.source_id == source.id,
            )
            .order_by(EvidenceItem.imported_at, EvidenceItem.id)
            .offset(offset)
            .limit(limit)
        )
    )
