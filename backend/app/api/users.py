"""User administration (ADMIN only) and the audit log."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_db_session, require_admin
from app.models import AuditAction, User, UserRole
from app.schemas import AuditLogOut, UserOut, UserUpdate
from app.services import audit_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)))


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono użytkownika.")
    changes = payload.model_dump(exclude_unset=True)

    if target.id == admin.id and (
        changes.get("role") not in (None, UserRole.ADMIN) or changes.get("is_active") is False
    ):
        raise HTTPException(
            status_code=400,
            detail="Nie można odebrać uprawnień własnemu kontu.",
        )
    if target.role is UserRole.ADMIN and changes.get("role") not in (None, UserRole.ADMIN):
        remaining = db.scalar(
            select(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True), User.id != target.id)
            .limit(1)
        )
        if remaining is None:
            raise HTTPException(
                status_code=400, detail="System musi mieć co najmniej jednego administratora."
            )

    for field, value in changes.items():
        setattr(target, field, value)
    db.flush()
    action = (
        AuditAction.USER_ROLE_CHANGED
        if "role" in changes
        else AuditAction.USER_ACTIVATION_CHANGED
    )
    audit_service.record(
        db,
        action,
        user=admin,
        entity_type="user",
        entity_id=target.id,
        metadata={"email": target.email, "changes": {k: str(v) for k, v in changes.items()}},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(target)
    return target


audit_router = APIRouter(prefix="/api/audit", tags=["audit"])


@audit_router.get("", response_model=list[AuditLogOut])
def list_audit(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> list[AuditLogOut]:
    return [
        AuditLogOut(
            id=row.id,
            user_id=row.user_id,
            user_email=row.user_email,
            action=row.action.value,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            timestamp=row.timestamp,
            metadata=row.meta,
        )
        for row in audit_service.recent(db, limit=limit, offset=offset)
    ]
