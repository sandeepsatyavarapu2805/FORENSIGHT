import uuid
from datetime import datetime
from typing import Literal

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
    case_kind: Literal["original", "investigation_copy"]
    parent_case_id: uuid.UUID | None
    evidence_case_id: uuid.UUID | None


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


class AskRequest(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=1000,
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError("query must not be blank")

        return value


class AskCitationResponse(BaseModel):
    evidence_id: str
    evidence_reference: str
    source_id: str
    artifact_type: str
    occurred_at: str | None
    application: str | None
    excerpt: str


class AskResponse(BaseModel):
    answer: str
    sufficient_evidence: bool
    citations: list[AskCitationResponse]


class FindingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    status: Literal["draft", "confirmed"] = "draft"
    evidence_references: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class FindingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: Literal["draft", "confirmed"] | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_null_or_blank(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("title must not be null")
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def description_must_not_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("description must not be null")
        return value


class FindingEvidenceAttach(BaseModel):
    evidence_reference: str = Field(min_length=1, max_length=80)


class FindingEvidenceResponse(BaseModel):
    id: uuid.UUID
    evidence_reference: str
    source_id: uuid.UUID
    artifact_type: str
    application: str | None
    occurred_at: datetime | None


class FindingResponse(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    title: str
    description: str
    status: Literal["draft", "confirmed"]
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    evidence: list[FindingEvidenceResponse]
    origin_proposal_id: uuid.UUID | None


class ReportSourceResponse(BaseModel):
    id: uuid.UUID
    label: str
    sha256: str | None
    parser_identifier: str | None
    parser_version: str | None
    is_partial: bool


class InvestigationReportResponse(BaseModel):
    case: CaseResponse
    investigator: UserResponse
    generated_at: datetime
    findings: list[FindingResponse]
    sources: list[ReportSourceResponse]
    warnings: list[str]


class GrantCreate(BaseModel):
    recipient_username: str = Field(min_length=1, max_length=100)
    duration_hours: Literal[24, 168, 720]


class GrantActivate(BaseModel):
    code: str = Field(min_length=20, max_length=200)


class GrantResponse(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    recipient_id: uuid.UUID
    recipient_username: str
    created_at: datetime
    expires_at: datetime
    activated_at: datetime | None
    revoked_at: datetime | None
    status: Literal["pending", "active", "expired", "revoked"]


class GrantCreatedResponse(GrantResponse):
    access_code: str


class AccessibleCaseResponse(BaseModel):
    case: CaseResponse
    grant_id: uuid.UUID
    access_level: Literal["temporary_read_only"]
    expires_at: datetime


class InvestigationCopyResponse(BaseModel):
    case: CaseResponse
    original_case: CaseResponse


class ProposedFindingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    evidence_references: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("title")
    @classmethod
    def proposal_title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class ProposedFindingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    evidence_references: list[str] | None = Field(default=None, max_length=200)


class ProposedFindingResponse(BaseModel):
    id: uuid.UUID
    source_copy_case_id: uuid.UUID
    original_case_id: uuid.UUID
    submitted_by_id: uuid.UUID
    title: str
    description: str
    status: Literal["draft", "submitted", "accepted", "rejected"]
    evidence: list[FindingEvidenceResponse]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_id: uuid.UUID | None
    accepted_finding_id: uuid.UUID | None


class ReauthenticateRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class ReauthenticateResponse(BaseModel):
    reauthenticated_until: datetime


class PrintAuthorizationResponse(BaseModel):
    authorized: bool
    authorized_at: datetime


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    case_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: uuid.UUID | None
    success: bool
    event_metadata: dict[str, object]
    occurred_at: datetime
