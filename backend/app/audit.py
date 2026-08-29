import uuid

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


def audit_event(
    db: Session,
    *,
    action: str,
    success: bool,
    user_id: uuid.UUID | None = None,
    case_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    metadata: dict[str, object] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user_id,
        case_id=case_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        success=success,
        event_metadata=metadata or {},
    )
    db.add(event)
    return event
