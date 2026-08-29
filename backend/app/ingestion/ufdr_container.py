import stat
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from app.config import settings
from app.ingestion.contracts import ParseResult, ParserFatalError, ValidationResult


@dataclass(frozen=True)
class ContainerLimits:
    maximum_members: int
    maximum_uncompressed_bytes: int
    maximum_compression_ratio: int
    maximum_report_xml_bytes: int


@dataclass(frozen=True)
class ContainerDiagnostic:
    severity: str
    code: str
    message: str
    archive_member: str | None = None


@dataclass(frozen=True)
class ContainerInspection:
    report_member: str
    member_count: int
    total_uncompressed_bytes: int
    report_xml_bytes: int
    root_element: str
    diagnostics: tuple[ContainerDiagnostic, ...]


class ContainerValidationError(Exception):
    def __init__(self, diagnostic: ContainerDiagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def configured_container_limits() -> ContainerLimits:
    return ContainerLimits(
        maximum_members=settings.archive_max_members,
        maximum_uncompressed_bytes=settings.archive_max_uncompressed_bytes,
        maximum_compression_ratio=settings.archive_max_compression_ratio,
        maximum_report_xml_bytes=settings.archive_max_report_xml_bytes,
    )


def _fail(code: str, message: str, member: str | None = None) -> None:
    raise ContainerValidationError(
        ContainerDiagnostic("error", code, message, archive_member=member)
    )


def _safe_member_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or (path.parts and ":" in path.parts[0])
    ):
        _fail("unsafe_archive_path", "Archive contains an unsafe member path", name)
    return path


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def inspect_ufdr_container(
    path: Path, limits: ContainerLimits | None = None
) -> ContainerInspection:
    limits = limits or configured_container_limits()
    if not zipfile.is_zipfile(path):
        _fail("not_zip_container", "Source is not a valid ZIP container")

    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > limits.maximum_members:
                _fail("too_many_members", "Archive contains too many members")

            seen_names: set[str] = set()
            report_info: zipfile.ZipInfo | None = None
            total_size = 0
            for info in members:
                member_path = _safe_member_name(info.filename)
                canonical_name = member_path.as_posix().casefold()
                if canonical_name in seen_names:
                    _fail(
                        "duplicate_archive_member",
                        "Archive contains duplicate member names",
                        info.filename,
                    )
                seen_names.add(canonical_name)

                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    _fail(
                        "archive_symlink_rejected",
                        "Archive symbolic links are not permitted",
                        info.filename,
                    )
                if info.flag_bits & 0x1:
                    _fail(
                        "encrypted_member_rejected",
                        "Encrypted archive members are not supported",
                        info.filename,
                    )
                if info.is_dir():
                    continue

                total_size += info.file_size
                if total_size > limits.maximum_uncompressed_bytes:
                    _fail(
                        "archive_expansion_limit",
                        "Archive exceeds the uncompressed size limit",
                    )
                if info.file_size and (
                    info.compress_size == 0
                    or info.file_size / info.compress_size
                    > limits.maximum_compression_ratio
                ):
                    _fail(
                        "suspicious_compression_ratio",
                        "Archive member exceeds the compression-ratio limit",
                        info.filename,
                    )
                if member_path.parts == ("report.xml",):
                    report_info = info

            if report_info is None:
                _fail(
                    "root_report_missing",
                    "ZIP container does not contain root report.xml",
                )
            if report_info.file_size > limits.maximum_report_xml_bytes:
                _fail("report_xml_too_large", "report.xml exceeds the XML size limit")

            with archive.open(report_info, "r") as report_stream:
                report_bytes = report_stream.read(limits.maximum_report_xml_bytes + 1)
            if len(report_bytes) > limits.maximum_report_xml_bytes:
                _fail("report_xml_too_large", "report.xml exceeds the XML size limit")
    except (zipfile.BadZipFile, OSError) as exc:
        _fail("invalid_zip_container", f"ZIP container could not be read: {exc}")

    try:
        root = SafeElementTree.fromstring(report_bytes)
    except DefusedXmlException:
        _fail("unsafe_xml", "report.xml contains prohibited DTD or entity content")
    except ParseError:
        _fail("malformed_report_xml", "report.xml is not well-formed XML")

    return ContainerInspection(
        report_member=report_info.filename,
        member_count=len(members),
        total_uncompressed_bytes=total_size,
        report_xml_bytes=len(report_bytes),
        root_element=_local_name(root.tag),
        diagnostics=(
            ContainerDiagnostic("info", "zip_container_valid", "ZIP structure validated"),
            ContainerDiagnostic(
                "info", "root_report_found", "Root report.xml discovered", "report.xml"
            ),
            ContainerDiagnostic(
                "info", "secure_xml_parsed", "report.xml passed secure XML parsing"
            ),
        ),
    )


def securely_parse_report_xml(path: Path, limits: ContainerLimits | None = None) -> Element:
    limits = limits or configured_container_limits()
    inspection = inspect_ufdr_container(path, limits)
    with zipfile.ZipFile(path) as archive:
        with archive.open(inspection.report_member, "r") as report_stream:
            report_bytes = report_stream.read(limits.maximum_report_xml_bytes + 1)
    try:
        return SafeElementTree.fromstring(report_bytes)
    except (DefusedXmlException, ParseError) as exc:
        raise ParserFatalError("Secure report.xml parsing failed") from exc


class UfdrZipAdapterBase(ABC):
    """Hook for a future sample-verified adapter; not registered as format support."""

    @abstractmethod
    def supports_filename(self, filename: str) -> bool: ...

    @property
    @abstractmethod
    def identifier(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    def validate(self, path: Path) -> ValidationResult:
        try:
            self.validate_report_structure(securely_parse_report_xml(path))
        except ContainerValidationError as exc:
            return ValidationResult(False, exc.diagnostic.message)
        except ParserFatalError as exc:
            return ValidationResult(False, str(exc))
        return ValidationResult(True)

    def parse(self, path: Path) -> ParseResult:
        root = securely_parse_report_xml(path)
        self.validate_report_structure(root)
        return self.parse_verified_report(root)

    @abstractmethod
    def validate_report_structure(self, root: Element) -> None: ...

    @abstractmethod
    def parse_verified_report(self, root: Element) -> ParseResult: ...
