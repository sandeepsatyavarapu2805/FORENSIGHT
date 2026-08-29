import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class CaseWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class CaseCreate(CaseWrite):
    pass


class CaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def name_must_not_be_null_or_blank(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("name must not be null")
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class CaseResponse(CaseWrite):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_identifier: str
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SourceCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("label")
    @classmethod
    def label_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("label must not be blank")
        return value


class SourceUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("label")
    @classmethod
    def label_must_not_be_null_or_blank(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("label must not be null")
        value = value.strip()
        if not value:
            raise ValueError("label must not be blank")
        return value


class SourceResponse(SourceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    original_filename: str | None
    file_size: int | None
    sha256: str | None
    imported_by_id: uuid.UUID | None
    imported_at: datetime | None
    parser_identifier: str | None
    parser_version: str | None
    processing_state: str
    processing_stage: str | None
    is_partial: bool
    error_summary: str | None
    evidence_count: int
    evidence_counts: dict[str, int]
    created_at: datetime
    updated_at: datetime


class ProcessingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    status: str
    stage: str | None
    progress: int | None
    diagnostics: list[dict[str, object]]
    stage_history: list[str]
    error_summary: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class EvidenceItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evidence_reference: str
    case_id: uuid.UUID
    source_id: uuid.UUID
    artifact_type: str
    original_record_id: str
    occurred_at: datetime | None
    application: str | None
    searchable_text: str
    parser_identifier: str
    parser_version: str
    imported_at: datetime


class EvidenceItemResponse(EvidenceItemSummary):
    data: dict[str, object]
    raw_metadata: dict[str, object]


class EvidencePageResponse(BaseModel):
    items: list[EvidenceItemSummary]
    total: int
    offset: int
    limit: int


class EvidenceFilterOptionsResponse(BaseModel):
    artifact_types: list[str]
    applications: list[str]


class AnalysisEntityResponse(BaseModel):
    key: str
    entity_type: str
    value: str
    evidence_ids: list[str]
    evidence_references: list[str]
    occurrence_count: int


class TimelineEntryResponse(BaseModel):
    evidence_id: str
    evidence_reference: str
    source_id: str
    artifact_type: str
    application: str | None
    occurred_at: datetime
    searchable_text: str


class RelationshipResponse(BaseModel):
    source_key: str
    target_key: str
    relationship_type: str
    evidence_ids: list[str]
    evidence_references: list[str]
    occurrence_count: int


class AnalysisOverviewResponse(BaseModel):
    entities: list[AnalysisEntityResponse]
    timeline: list[TimelineEntryResponse]
    relationships: list[RelationshipResponse]
    warnings: list[str]
