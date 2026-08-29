from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    error: str | None = None


@dataclass(frozen=True)
class ParserDiagnostic:
    severity: str
    code: str
    message: str
    original_reference: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "original_reference": self.original_reference,
        }


@dataclass(frozen=True)
class ParsedArtifact:
    artifact_type: str
    original_record_id: str
    searchable_text: str
    data: dict[str, object]
    raw_metadata: dict[str, object]
    occurred_at: datetime | None = None
    application: str | None = None


@dataclass(frozen=True)
class ParseResult:
    artifacts: Iterable[ParsedArtifact]
    diagnostics: list[ParserDiagnostic] = field(default_factory=list)


class ParserFatalError(Exception):
    pass


class ParserAdapter(Protocol):
    identifier: str
    version: str

    def supports_filename(self, filename: str) -> bool: ...

    def validate(self, path: Path) -> ValidationResult: ...

    def parse(self, path: Path) -> ParseResult: ...
