import stat
import zipfile
from pathlib import Path

import pytest

from app.ingestion.registry import parser_registry
from app.ingestion.ufdr_container import (
    ContainerLimits,
    ContainerValidationError,
    inspect_ufdr_container,
    securely_parse_report_xml,
)


def limits(**overrides: int) -> ContainerLimits:
    values = {
        "maximum_members": 20,
        "maximum_uncompressed_bytes": 1_000_000,
        "maximum_compression_ratio": 1_000,
        "maximum_report_xml_bytes": 100_000,
    }
    values.update(overrides)
    return ContainerLimits(**values)


def write_archive(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def assert_container_error(path: Path, code: str, test_limits: ContainerLimits | None = None) -> None:
    with pytest.raises(ContainerValidationError) as caught:
        inspect_ufdr_container(path, test_limits or limits())
    assert caught.value.diagnostic.code == code


def test_valid_zip_discovers_only_root_report_and_parses_xml_securely(tmp_path: Path) -> None:
    archive = write_archive(
        tmp_path / "container.ufdr",
        {
            "report.xml": b'<ufdr:Report xmlns:ufdr="urn:test"><Section /></ufdr:Report>',
            "files/attachment.bin": b"preserved attachment",
        },
    )

    inspection = inspect_ufdr_container(archive, limits())
    root = securely_parse_report_xml(archive, limits())

    assert inspection.report_member == "report.xml"
    assert inspection.member_count == 2
    assert inspection.root_element == "Report"
    assert [item.code for item in inspection.diagnostics] == [
        "zip_container_valid",
        "root_report_found",
        "secure_xml_parsed",
    ]
    assert root.tag == "{urn:test}Report"


def test_non_zip_missing_or_nested_report_is_rejected(tmp_path: Path) -> None:
    plain = tmp_path / "plain.ufdr"
    plain.write_bytes(b"not a zip")
    assert_container_error(plain, "not_zip_container")

    missing = write_archive(tmp_path / "missing.ufdr", {"other.xml": b"<Report />"})
    assert_container_error(missing, "root_report_missing")

    nested = write_archive(
        tmp_path / "nested.ufdr", {"folder/report.xml": b"<Report />"}
    )
    assert_container_error(nested, "root_report_missing")


@pytest.mark.parametrize("member", ["../escape.txt", "/absolute.txt", "C:/drive.txt"])
def test_archive_traversal_and_absolute_paths_are_rejected(
    tmp_path: Path, member: str
) -> None:
    archive = write_archive(
        tmp_path / "unsafe.ufdr",
        {"report.xml": b"<Report />", member: b"unsafe"},
    )
    assert_container_error(archive, "unsafe_archive_path")


def test_symlinks_and_suspicious_expansion_are_rejected(tmp_path: Path) -> None:
    symlink_archive = tmp_path / "symlink.ufdr"
    with zipfile.ZipFile(symlink_archive, "w") as archive:
        archive.writestr("report.xml", b"<Report />")
        link = zipfile.ZipInfo("linked-file")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"target")
    assert_container_error(symlink_archive, "archive_symlink_rejected")

    expanded = write_archive(
        tmp_path / "expanded.ufdr", {"report.xml": b"<Report>" + b"A" * 20_000 + b"</Report>"}
    )
    assert_container_error(
        expanded,
        "suspicious_compression_ratio",
        limits(maximum_compression_ratio=2),
    )


def test_malformed_and_entity_xml_are_rejected(tmp_path: Path) -> None:
    malformed = write_archive(
        tmp_path / "malformed.ufdr", {"report.xml": b"<Report>"}
    )
    assert_container_error(malformed, "malformed_report_xml")

    entity = write_archive(
        tmp_path / "entity.ufdr",
        {
            "report.xml": (
                b'<!DOCTYPE Report [<!ENTITY secret "forbidden">]>'
                b"<Report>&secret;</Report>"
            )
        },
    )
    assert_container_error(entity, "unsafe_xml")


def test_container_hooks_do_not_claim_production_parser_support() -> None:
    assert parser_registry.for_filename("representative.ufdr") is None
    assert parser_registry.for_filename("representative.zip") is None
