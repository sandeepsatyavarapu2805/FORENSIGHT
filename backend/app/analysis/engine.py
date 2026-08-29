from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource


@dataclass(frozen=True)
class AnalysisEntity:
    key: str
    entity_type: str
    value: str
    evidence_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]
    occurrence_count: int


@dataclass(frozen=True)
class TimelineEntry:
    evidence_id: str
    evidence_reference: str
    source_id: str
    artifact_type: str
    application: str | None
    occurred_at: datetime
    searchable_text: str


@dataclass(frozen=True)
class Relationship:
    source_key: str
    target_key: str
    relationship_type: str
    evidence_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]
    occurrence_count: int


def _clean_entity_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()

    if not cleaned:
        return None

    return cleaned


def _explicit_entities(item: EvidenceItem) -> list[tuple[str, str]]:
    """
    Read optional explicitly normalized entity data.

    Parsers may place a list under data["entities"] in the form:

        {
            "entities": [
                {"type": "person", "value": "Example Name"},
                {"type": "phone", "value": "+911234567890"}
            ]
        }

    Unknown or malformed entries are ignored rather than inferred.
    """
    raw_entities = item.data.get("entities")

    if not isinstance(raw_entities, list):
        return []

    entities: list[tuple[str, str]] = []

    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            continue

        entity_type = _clean_entity_value(raw_entity.get("type"))
        value = _clean_entity_value(raw_entity.get("value"))

        if entity_type is None or value is None:
            continue

        entities.append((entity_type.lower(), value))

    return entities


def build_entities(
    evidence_items: list[EvidenceItem],
) -> list[AnalysisEntity]:
    grouped: dict[
        tuple[str, str],
        dict[str, set[str] | int],
    ] = {}

    for item in evidence_items:
        candidates = _explicit_entities(item)

        if item.application:
            candidates.append(("application", item.application.strip()))

        for entity_type, value in candidates:
            normalized_value = value.casefold()
            group_key = (entity_type, normalized_value)

            if group_key not in grouped:
                grouped[group_key] = {
                    "ids": set(),
                    "references": set(),
                    "count": 0,
                }

            group = grouped[group_key]

            ids = group["ids"]
            references = group["references"]

            assert isinstance(ids, set)
            assert isinstance(references, set)

            ids.add(str(item.id))
            references.add(item.evidence_reference)

            count = group["count"]
            assert isinstance(count, int)
            group["count"] = count + 1

    result: list[AnalysisEntity] = []

    for (entity_type, normalized_value), group in grouped.items():
        ids = group["ids"]
        references = group["references"]
        count = group["count"]

        assert isinstance(ids, set)
        assert isinstance(references, set)
        assert isinstance(count, int)

        display_value = normalized_value

        for item in evidence_items:
            for candidate_type, candidate_value in [
                *_explicit_entities(item),
                *(
                    [("application", item.application.strip())]
                    if item.application
                    else []
                ),
            ]:
                if (
                    candidate_type == entity_type
                    and candidate_value.casefold() == normalized_value
                ):
                    display_value = candidate_value
                    break

        result.append(
            AnalysisEntity(
                key=f"{entity_type}:{normalized_value}",
                entity_type=entity_type,
                value=display_value,
                evidence_ids=tuple(sorted(ids)),
                evidence_references=tuple(sorted(references)),
                occurrence_count=count,
            )
        )

    return sorted(
        result,
        key=lambda entity: (
            entity.entity_type,
            entity.value.casefold(),
        ),
    )


def build_timeline(
    evidence_items: list[EvidenceItem],
) -> list[TimelineEntry]:
    entries = [
        TimelineEntry(
            evidence_id=str(item.id),
            evidence_reference=item.evidence_reference,
            source_id=str(item.source_id),
            artifact_type=item.artifact_type,
            application=item.application,
            occurred_at=item.occurred_at,
            searchable_text=item.searchable_text,
        )
        for item in evidence_items
        if item.occurred_at is not None
    ]

    return sorted(
        entries,
        key=lambda entry: (
            entry.occurred_at,
            entry.evidence_reference,
        ),
    )


def build_relationships(
    evidence_items: list[EvidenceItem],
) -> list[Relationship]:
    relationship_evidence: dict[
        tuple[str, str, str],
        dict[str, set[str] | int],
    ] = defaultdict(
        lambda: {
            "ids": set(),
            "references": set(),
            "count": 0,
        }
    )

    for item in evidence_items:
        entities = _explicit_entities(item)

        if item.application:
            entities.append(("application", item.application.strip()))

        unique_keys = sorted(
            {
                f"{entity_type}:{value.casefold()}"
                for entity_type, value in entities
            }
        )

        for index, source_key in enumerate(unique_keys):
            for target_key in unique_keys[index + 1 :]:
                group = relationship_evidence[
                    (source_key, target_key, "co_occurrence")
                ]

                ids = group["ids"]
                references = group["references"]

                assert isinstance(ids, set)
                assert isinstance(references, set)

                ids.add(str(item.id))
                references.add(item.evidence_reference)

                count = group["count"]
                assert isinstance(count, int)
                group["count"] = count + 1

    relationships: list[Relationship] = []

    for (
        source_key,
        target_key,
        relationship_type,
    ), group in relationship_evidence.items():
        ids = group["ids"]
        references = group["references"]
        count = group["count"]

        assert isinstance(ids, set)
        assert isinstance(references, set)
        assert isinstance(count, int)

        relationships.append(
            Relationship(
                source_key=source_key,
                target_key=target_key,
                relationship_type=relationship_type,
                evidence_ids=tuple(sorted(ids)),
                evidence_references=tuple(sorted(references)),
                occurrence_count=count,
            )
        )

    return sorted(
        relationships,
        key=lambda relationship: (
            relationship.source_key,
            relationship.target_key,
        ),
    )


def source_warnings(
    sources: list[EvidenceSource],
) -> list[str]:
    warnings: list[str] = []

    for source in sources:
        if source.is_partial:
            warnings.append(
                f"{source.label}: Source partially parsed — continue with caution."
            )

    return warnings