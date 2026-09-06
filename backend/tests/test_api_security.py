"""Spec tests 18-22 - authentication, RBAC, OAuth state/nonce, CSRF."""
from __future__ import annotations

import pytest

from app.config import settings

PROTECTED = [
    ("GET", "/api/employees"),
    ("GET", "/api/schedules/2026/9"),
    ("GET", "/api/availability"),
    ("GET", "/api/holidays/2026"),
    ("GET", "/api/settings"),
    ("GET", "/api/dashboard"),
    ("GET", "/api/users"),
    ("GET", "/api/audit"),
]

ADMIN_ONLY = [
    ("GET", "/api/users", None),
    ("GET", "/api/audit", None),
    ("PUT", "/api/settings", {"facility_name": "Przejete"}),
]


# --- 21. no API access without a session ---------------------------------
@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_endpoints_require_a_session(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 401
    assert "sesji" in response.json()["detail"]


def test_health_is_public(client):
    assert client.get("/api/health").status_code == 200


# --- 18. authentication ---------------------------------------------------
def test_login_creates_a_user_and_a_session(client, seeded):
    assert client.get("/api/auth/status").json()["authenticated"] is False

    response = client.post("/api/auth/dev-login")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == settings.dev_auth_email
    assert body["role"] == "ADMIN"  # first account ever becomes ADMIN

    status = client.get("/api/auth/status").json()
    assert status["authenticated"] is True
    assert status["user"]["email"] == settings.dev_auth_email

    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["id"] == body["id"]


def test_session_cookie_is_http_only(client, seeded):
    response = client.post("/api/auth/dev-login")
    cookie_header = "".join(response.headers.get_list("set-cookie"))
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header.lower() or "samesite=lax" in cookie_header.lower()


def test_logout_ends_the_session(logged_in):
    assert logged_in.post("/api/auth/logout").status_code == 200
    assert logged_in.get("/api/employees").status_code == 401


def test_tampered_session_cookie_is_rejected(client, seeded):
    client.post("/api/auth/dev-login")
    client.cookies.set(settings.session_cookie_name, "forged.cookie.value")
    assert client.get("/api/employees").status_code == 401


def test_login_is_audited(logged_in, db_session):
    from app.models import AuditAction, AuditLog

    actions = [row.action for row in db_session.query(AuditLog).all()]
    assert AuditAction.LOGIN in actions


# --- 19 & 22. RBAC --------------------------------------------------------
@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ONLY)
def test_manager_cannot_reach_admin_endpoints(manager_client, method, path, payload):
    response = manager_client.request(method, path, json=payload)
    assert response.status_code == 403
    assert "uprawnien" in response.json()["detail"]


def test_manager_can_use_the_scheduling_workflow(manager_client):
    assert manager_client.get("/api/employees").status_code == 200
    assert manager_client.get("/api/schedules/2026/9").status_code == 200
    assert manager_client.get("/api/settings").status_code == 200  # read-only is fine


def test_admin_can_reach_admin_endpoints(logged_in):
    assert logged_in.get("/api/users").status_code == 200
    assert logged_in.get("/api/audit").status_code == 200
    assert logged_in.put("/api/settings", json={"facility_name": "Szpital MSW"}).status_code == 200


def test_role_change_is_picked_up_without_a_relogin(logged_in, db_engine):
    """A downgraded session must lose its ADMIN powers immediately."""
    import sqlalchemy as sa

    assert logged_in.get("/api/users").status_code == 200
    with db_engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET role = 'MANAGER'"))
    assert logged_in.get("/api/users").status_code == 403


def test_deactivated_user_loses_access(logged_in, db_engine):
    import sqlalchemy as sa

    with db_engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_active = false"))
    assert logged_in.get("/api/employees").status_code == 401


def test_last_admin_cannot_be_demoted(logged_in):
    me = logged_in.get("/api/auth/me").json()
    response = logged_in.put(f"/api/users/{me['id']}", json={"role": "MANAGER"})
    assert response.status_code == 400
    assert "wlasnemu kontu" in response.json()["detail"]


# --- CSRF -----------------------------------------------------------------
def test_write_without_csrf_header_is_refused(logged_in):
    logged_in.headers.pop("X-CSRF-Token", None)
    response = logged_in.post("/api/employees", json={
        "first_name": "Test", "last_name": "Testowa", "role": "NURSE",
        "employment_date": "2020-01-01", "active": True,
    })
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_write_with_a_wrong_csrf_token_is_refused(logged_in):
    logged_in.headers["X-CSRF-Token"] = "not-the-right-token"
    response = logged_in.post("/api/employees", json={
        "first_name": "Test", "last_name": "Testowa", "role": "NURSE",
        "employment_date": "2020-01-01", "active": True,
    })
    assert response.status_code == 403


def test_reads_do_not_need_a_csrf_header(logged_in):
    logged_in.headers.pop("X-CSRF-Token", None)
    assert logged_in.get("/api/employees").status_code == 200


# --- 20. OAuth state and nonce -------------------------------------------
def test_oauth_state_cookie_is_signed_and_round_trips():
    from fastapi import Response

    from app.security import session as session_module

    response = Response()
    state, nonce = session_module.issue_oauth_state(response, "/grafik")
    raw = response.headers["set-cookie"].split("=", 1)[1].split(";")[0]

    class FakeRequest:
        cookies = {session_module.OAUTH_STATE_COOKIE: raw}

    stored = session_module.read_oauth_state(FakeRequest())
    assert stored == {"state": state, "nonce": nonce, "redirect_to": "/grafik"}


def test_forged_oauth_state_cookie_is_rejected():
    from app.security import session as session_module

    class FakeRequest:
        cookies = {session_module.OAUTH_STATE_COOKIE: "eyJzdGF0ZSI6ICJhdHRhY2tlciJ9.forged"}

    assert session_module.read_oauth_state(FakeRequest()) is None


def test_callback_without_a_state_cookie_is_refused(client):
    response = client.get(
        "/api/auth/google/callback?code=abc&state=xyz", follow_redirects=False
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]


def test_callback_with_a_mismatched_state_is_refused(client):
    from fastapi import Response

    from app.security import session as session_module

    holder = Response()
    session_module.issue_oauth_state(holder, None)
    raw = holder.headers["set-cookie"].split("=", 1)[1].split(";")[0]
    client.cookies.set(session_module.OAUTH_STATE_COOKIE, raw)

    response = client.get(
        "/api/auth/google/callback?code=abc&state=WRONG", follow_redirects=False
    )
    assert response.status_code == 303
    assert "state" in response.headers["location"]


def test_id_token_with_a_wrong_nonce_is_rejected(monkeypatch):
    """verify_id_token must refuse a token whose nonce does not match."""
    from app.security import oauth

    class FakeClaims(dict):
        def validate(self, leeway=0):
            return None

    monkeypatch.setattr(oauth, "_jwks", lambda: object())
    monkeypatch.setattr(
        oauth.JsonWebToken,
        "decode",
        lambda self, token, key, claims_options=None: FakeClaims(
            {
                "iss": "https://accounts.google.com",
                "aud": "client",
                "sub": "123",
                "email": "a@b.pl",
                "email_verified": True,
                "nonce": "the-real-nonce",
            }
        ),
    )
    with pytest.raises(oauth.OAuthError, match="nonce"):
        oauth.verify_id_token("token", "a-different-nonce")

    identity = oauth.verify_id_token("token", "the-real-nonce")
    assert identity.subject == "123" and identity.email == "a@b.pl"


def test_unverified_google_email_is_rejected(monkeypatch):
    from app.security import oauth

    class FakeClaims(dict):
        def validate(self, leeway=0):
            return None

    monkeypatch.setattr(oauth, "_jwks", lambda: object())
    monkeypatch.setattr(
        oauth.JsonWebToken,
        "decode",
        lambda self, token, key, claims_options=None: FakeClaims(
            {"sub": "1", "email": "a@b.pl", "email_verified": False, "nonce": "n"}
        ),
    )
    with pytest.raises(oauth.OAuthError, match="zweryfikowany"):
        oauth.verify_id_token("token", "n")


# --- security headers -----------------------------------------------------
def test_security_headers_are_present(client):
    headers = client.get("/api/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "Content-Security-Policy" in headers


def test_rate_limiter_blocks_a_flood(client, monkeypatch):
    """The auth bucket is deliberately tight (brute-force protection)."""
    from app.config import settings as live

    monkeypatch.setattr(live, "rate_limit_enabled", True)
    monkeypatch.setattr(live, "rate_limit_auth", 3)

    statuses = [client.get("/api/auth/status").status_code for _ in range(6)]
    assert 429 in statuses
    blocked = client.get("/api/auth/status")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


# --- new accounts must be approved before they get in ---------------------
def _google_identity(email: str, subject: str):
    from app.security.oauth import GoogleIdentity

    return GoogleIdentity(
        subject=subject,
        email=email,
        email_verified=True,
        name="Nowa Osoba",
        picture=None,
        hosted_domain=None,
    )


def test_first_account_ever_is_an_active_admin(db_session):
    from app.services import user_service

    user = user_service.upsert_from_google(db_session, _google_identity("first@x.pl", "s1"))
    db_session.commit()
    assert user.role.value == "ADMIN"
    assert user.is_active is True


def test_a_second_google_account_is_created_locked(db_session):
    """Passing Google's login only proves identity, not authorisation."""
    from app.services import user_service

    user_service.upsert_from_google(db_session, _google_identity("first@x.pl", "s1"))
    db_session.commit()

    stranger = user_service.upsert_from_google(
        db_session, _google_identity("stranger@gmail.com", "s2")
    )
    db_session.commit()
    assert stranger.role.value == "MANAGER"
    assert stranger.is_active is False, "an unknown Google account must not get access"


def test_listed_admin_email_is_active_immediately(db_session, monkeypatch):
    from app.config import settings as live
    from app.services import user_service

    user_service.upsert_from_google(db_session, _google_identity("first@x.pl", "s1"))
    db_session.commit()

    monkeypatch.setattr(
        type(live), "admin_emails", property(lambda self: {"boss@x.pl"})
    )
    boss = user_service.upsert_from_google(db_session, _google_identity("boss@x.pl", "s3"))
    db_session.commit()
    assert boss.role.value == "ADMIN"
    assert boss.is_active is True


def test_auto_activation_can_be_turned_on_deliberately(db_session, monkeypatch):
    from app.config import settings as live
    from app.services import user_service

    user_service.upsert_from_google(db_session, _google_identity("first@x.pl", "s1"))
    db_session.commit()

    monkeypatch.setattr(live, "auto_activate_new_users", True)
    guest = user_service.upsert_from_google(db_session, _google_identity("guest@x.pl", "s4"))
    db_session.commit()
    assert guest.is_active is True


def test_locked_account_cannot_use_the_api(client, seeded, db_engine):
    """Even with a valid session cookie, a locked account is refused."""
    import sqlalchemy as sa

    client.post("/api/auth/dev-login")
    client.headers["X-CSRF-Token"] = client.cookies.get(settings.csrf_cookie_name)
    assert client.get("/api/employees").status_code == 200

    with db_engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_active = false"))

    response = client.get("/api/employees")
    assert response.status_code == 401
    assert "aktywacje" in response.json()["detail"]


def test_admin_can_activate_a_pending_account(logged_in, db_session):
    from app.services import user_service

    pending = user_service.upsert_from_google(
        db_session, _google_identity("pending@x.pl", "s9")
    )
    db_session.commit()
    assert pending.is_active is False

    listed = {u["email"]: u for u in logged_in.get("/api/users").json()}
    assert listed["pending@x.pl"]["is_active"] is False

    response = logged_in.put(f"/api/users/{pending.id}", json={"is_active": True})
    assert response.status_code == 200
    assert response.json()["is_active"] is True
