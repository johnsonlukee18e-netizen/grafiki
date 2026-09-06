"""User provisioning from a verified Google identity."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, UserRole
from app.security.oauth import GoogleIdentity


def by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def user_count(db: Session) -> int:
    return db.scalar(select(func.count(User.id))) or 0


def _initial_role(db: Session, email: str) -> UserRole:
    """First user ever, or an e-mail listed in INITIAL_ADMIN_EMAILS, is ADMIN."""
    if email.lower() in settings.admin_emails:
        return UserRole.ADMIN
    if user_count(db) == 0:
        return UserRole.ADMIN
    return UserRole.MANAGER


def upsert_from_google(db: Session, identity: GoogleIdentity) -> User:
    """Find or create the account behind a verified Google login."""
    user = db.scalar(select(User).where(User.google_subject_id == identity.subject))
    if user is None:
        user = by_email(db, identity.email)
    if user is None:
        user = User(
            google_subject_id=identity.subject,
            email=identity.email,
            name=identity.name,
            avatar_url=identity.picture,
            role=_initial_role(db, identity.email),
            is_active=True,
        )
        db.add(user)
    else:
        user.google_subject_id = identity.subject
        user.email = identity.email
        user.name = identity.name or user.name
        user.avatar_url = identity.picture or user.avatar_url
    user.last_login_at = datetime.now(UTC)
    db.flush()
    return user


def upsert_dev_user(db: Session, email: str) -> User:
    """Development-only shortcut; never reachable when APP_ENV=production."""
    user = by_email(db, email)
    if user is None:
        user = User(
            email=email.lower(),
            name="Konto deweloperskie",
            role=_initial_role(db, email),
            is_active=True,
        )
        db.add(user)
    user.last_login_at = datetime.now(UTC)
    db.flush()
    return user
