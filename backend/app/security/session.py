"""Stateless, signed session cookies.

The browser only ever receives an HMAC-signed payload in an HTTP-only cookie;
no token is readable by JavaScript and nothing is kept in localStorage.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

SESSION_SALT = "nurse-session-v1"
OAUTH_STATE_SALT = "nurse-oauth-state-v1"
OAUTH_STATE_COOKIE = "nurse_oauth"
OAUTH_STATE_MAX_AGE = 600  # 10 minutes to complete the Google round trip

_session_serializer = URLSafeTimedSerializer(settings.session_secret, salt=SESSION_SALT)
_state_serializer = URLSafeTimedSerializer(settings.session_secret, salt=OAUTH_STATE_SALT)


@dataclass(frozen=True)
class SessionData:
    user_id: int
    email: str
    role: str
    csrf: str
    issued_at: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "uid": self.user_id,
            "email": self.email,
            "role": self.role,
            "csrf": self.csrf,
            "iat": self.issued_at,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SessionData:
        return cls(
            user_id=int(payload["uid"]),
            email=str(payload["email"]),
            role=str(payload["role"]),
            csrf=str(payload["csrf"]),
            issued_at=int(payload.get("iat", 0)),
        )


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _cookie_kwargs() -> dict[str, Any]:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
    }


def issue_session(response: Response, user_id: int, email: str, role: str) -> SessionData:
    data = SessionData(
        user_id=user_id,
        email=email,
        role=role,
        csrf=new_csrf_token(),
        issued_at=int(time.time()),
    )
    token = _session_serializer.dumps(data.as_payload())
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age_seconds,
        **_cookie_kwargs(),
    )
    # Readable by the SPA so it can echo the value back in a header
    # (double-submit CSRF protection).
    response.set_cookie(
        settings.csrf_cookie_name,
        data.csrf,
        max_age=settings.session_max_age_seconds,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return data


def read_session(request: Request) -> SessionData | None:
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        return None
    try:
        payload = _session_serializer.loads(raw, max_age=settings.session_max_age_seconds)
    except (SignatureExpired, BadSignature, ValueError):
        return None
    try:
        return SessionData.from_payload(payload)
    except (KeyError, TypeError, ValueError):
        return None


def refresh_session(response: Response, data: SessionData) -> None:
    """Slide the expiry window without changing the CSRF token."""
    token = _session_serializer.dumps(data.as_payload())
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age_seconds,
        **_cookie_kwargs(),
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def should_refresh(data: SessionData) -> bool:
    age = int(time.time()) - data.issued_at
    return age > settings.session_idle_timeout_seconds


# --- OAuth state / nonce --------------------------------------------------
def issue_oauth_state(response: Response, redirect_to: str | None = None) -> tuple[str, str]:
    """Create a signed state+nonce pair and stash it in a short-lived cookie."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    token = _state_serializer.dumps(
        {"state": state, "nonce": nonce, "redirect_to": redirect_to or ""}
    )
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        token,
        max_age=OAUTH_STATE_MAX_AGE,
        **_cookie_kwargs(),
    )
    return state, nonce


def read_oauth_state(request: Request) -> dict[str, str] | None:
    raw = request.cookies.get(OAUTH_STATE_COOKIE)
    if not raw:
        return None
    try:
        return _state_serializer.loads(raw, max_age=OAUTH_STATE_MAX_AGE)
    except (SignatureExpired, BadSignature, ValueError):
        return None


def clear_oauth_state(response: Response) -> None:
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
