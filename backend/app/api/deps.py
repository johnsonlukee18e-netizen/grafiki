"""Shared FastAPI dependencies: database session, current user, RBAC.

Authorisation is enforced here, on the backend. Hiding a button in the SPA is
never treated as a permission check.
"""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import User, UserRole
from app.security import session as session_module

__all__ = ["get_db_session", "current_user", "require_admin", "require_manager", "client_ip"]


def get_db_session() -> Iterator[Session]:
    yield from get_db()


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def current_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> User:
    """Resolve the signed session cookie into a live, active user."""
    data = session_module.read_session(request)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Brak aktywnej sesji. Zaloguj sie ponownie.",
        )
    user = db.get(User, data.user_id)
    if user is None or not user.is_active:
        session_module.clear_session(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Konto nie istnieje lub zostalo dezaktywowane.",
        )
    if user.role.value != data.role:
        # The role changed since the cookie was issued - re-issue it so the
        # session can never keep stale (higher) privileges.
        session_module.issue_session(response, user.id, user.email, user.role.value)
    elif session_module.should_refresh(data):
        session_module.refresh_session(response, data)
    return user


def require_manager(user: User = Depends(current_user)) -> User:
    """Both roles may run the scheduling workflow."""
    if user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nie masz uprawnien do wykonania tej operacji.",
        )
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nie masz uprawnien do wykonania tej operacji. Wymagana rola ADMIN.",
        )
    return user
