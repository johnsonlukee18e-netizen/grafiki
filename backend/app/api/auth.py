"""Authentication endpoints - Google OAuth only, no passwords anywhere."""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user, get_db_session
from app.config import settings
from app.models import AuditAction, User
from app.schemas import AuthStatus, UserOut
from app.security import oauth
from app.security import session as session_module
from app.services import audit_service, user_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _login_redirect(message: str) -> RedirectResponse:
    target = f"{settings.frontend_url.rstrip('/')}/login?error={quote(message)}"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/google", summary="Start the Google authorization code flow")
def google_login(request: Request, redirect_to: str | None = None) -> RedirectResponse:
    response = RedirectResponse("about:blank", status_code=status.HTTP_303_SEE_OTHER)
    state, nonce = session_module.issue_oauth_state(response, redirect_to)
    try:
        url = oauth.authorization_url(state, nonce)
    except oauth.OAuthError as exc:
        logger.warning("OAuth start failed: %s", exc)
        return _login_redirect(str(exc))
    response.headers["location"] = url
    return response


@router.get("/google/callback", summary="Google redirects here with the code")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    if error:
        logger.info("Google returned an error to the callback")
        return _login_redirect("Logowanie zostalo przerwane.")

    stored = session_module.read_oauth_state(request)
    if stored is None:
        return _login_redirect("Sesja logowania wygasla. Sprobuj ponownie.")
    if not state or not code or state != stored.get("state"):
        return _login_redirect("Nieprawidlowy parametr state - logowanie odrzucone.")

    try:
        tokens = oauth.exchange_code(code)
        identity = oauth.verify_id_token(tokens["id_token"], stored.get("nonce", ""))
    except oauth.OAuthError as exc:
        return _login_redirect(str(exc))

    user = user_service.upsert_from_google(db, identity)
    if not user.is_active:
        db.commit()
        return _login_redirect("Konto zostalo dezaktywowane. Skontaktuj sie z administratorem.")

    audit_service.record(
        db,
        AuditAction.LOGIN,
        user=user,
        entity_type="user",
        entity_id=user.id,
        metadata={"method": "google"},
        ip_address=client_ip(request),
    )
    db.commit()

    destination = stored.get("redirect_to") or "/"
    if not destination.startswith("/"):
        destination = "/"  # never redirect off-site
    response = RedirectResponse(
        f"{settings.frontend_url.rstrip('/')}{destination}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    session_module.issue_session(response, user.id, user.email, user.role.value)
    session_module.clear_oauth_state(response)
    return response


@router.post("/dev-login", summary="Development-only login (disabled in production)")
def dev_login(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> UserOut:
    if not settings.dev_auth_allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
        )
    user = user_service.upsert_dev_user(db, settings.dev_auth_email)
    audit_service.record(
        db,
        AuditAction.LOGIN,
        user=user,
        entity_type="user",
        entity_id=user.id,
        metadata={"method": "dev"},
        ip_address=client_ip(request),
    )
    db.commit()
    session_module.issue_session(response, user.id, user.email, user.role.value)
    return UserOut.model_validate(user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> dict[str, bool]:
    data = session_module.read_session(request)
    if data is not None:
        user = db.get(User, data.user_id)
        audit_service.record(
            db,
            AuditAction.LOGOUT,
            user=user,
            entity_type="user",
            entity_id=data.user_id,
            ip_address=client_ip(request),
        )
        db.commit()
    session_module.clear_session(response)
    return {"success": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.get("/status", response_model=AuthStatus, summary="Session probe for the SPA")
def auth_status(request: Request, db: Session = Depends(get_db_session)) -> AuthStatus:
    data = session_module.read_session(request)
    user = db.get(User, data.user_id) if data else None
    authenticated = bool(user and user.is_active)
    return AuthStatus(
        authenticated=authenticated,
        user=UserOut.model_validate(user) if authenticated else None,
        oauth_configured=settings.oauth_configured,
        dev_auth_enabled=settings.dev_auth_allowed,
    )
