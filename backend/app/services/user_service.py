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


def _is_bootstrap_admin(db: Session, email: str) -> bool:
    """Listed in INITIAL_ADMIN_EMAILS, or the very first account in the system.

    The first account has to be an active administrator, otherwise nobody
    could ever activate anybody.
    """
    return email.lower() in settings.admin_emails or user_count(db) == 0


def _initial_role(db: Session, email: str) -> UserRole:
    return UserRole.ADMIN if _is_bootstrap_admin(db, email) else UserRole.MANAGER


def _initial_active(db: Session, email: str) -> bool:
    """Whether a newly created account may use the system straight away.

    Authenticating with Google says who somebody is; it does not say they are
    allowed in here. Every account that is not a bootstrap administrator is
    therefore created locked and waits for an ADMIN to activate it.
    """
    return _is_bootstrap_admin(db, email) or settings.auto_activate_new_users


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
            is_active=_initial_active(db, identity.email),
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
