"""Synthetic parser used only to verify the parser-neutral ingestion contract."""

from datetime import UTC, datetime
from pathlib import Path

from app.ingestion.contracts import (
    ParsedArtifact,
    ParseResult,
    ParserDiagnostic,
    ParserFatalError,
    ValidationResult,
)


class SyntheticParserAdapter:
    identifier = "test.synthetic"
    version = "1"

    def supports_filename(self, filename: str) -> bool:
        return filename.lower().endswith(".synthetic")

    def validate(self, path: Path) -> ValidationResult:
        marker = path.read_bytes().splitlines()[0] if path.stat().st_size else b""
        if marker not in {b"VALID", b"PARTIAL", b"FATAL"}:
            return ValidationResult(False, "Synthetic fixture has an invalid marker")
        return ValidationResult(True)

    def parse(self, path: Path) -> ParseResult:
        marker = path.read_bytes().splitlines()[0]
        if marker == b"FATAL":
            raise ParserFatalError("Synthetic fatal format error")

        message = ParsedArtifact(
            artifact_type="message",
            original_record_id="message-1",
            occurred_at=datetime(2025, 1, 2, 3, 4, tzinfo=UTC),
            application="Synthetic Chat",
            searchable_text="hello from the synthetic fixture",
            data={"sender": "Alice", "body": "hello"},
            raw_metadata={"fixture_line": 1},
        )
        if marker == b"PARTIAL":
            return ParseResult(
                artifacts=[message],
                diagnostics=[
                    ParserDiagnostic(
                        severity="error",
                        code="synthetic_bad_record",
                        message="A deliberately malformed synthetic record was skipped",
                        original_reference="bad-2",
                    )
                ],
            )

        contact = ParsedArtifact(
            artifact_type="contact",
            original_record_id="contact-1",
            searchable_text="Alice +15550000001",
            data={"name": "Alice", "phone": "+15550000001"},
            raw_metadata={"fixture_line": 2},
        )
        return ParseResult(artifacts=[message, contact])
