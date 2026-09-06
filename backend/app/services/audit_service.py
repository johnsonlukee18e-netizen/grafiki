"""Audit trail - every meaningful change is recorded."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditAction, AuditLog, User


def record(
    db: Session,
    action: AuditAction,
    *,
    user: User | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=metadata,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry


def recent(db: Session, limit: int = 100, offset: int = 0) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
