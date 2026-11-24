"""Google OAuth 2.0 / OpenID Connect - proper Authorization Code Flow.

The browser never hands us identity data: the backend exchanges the code
server-side and validates the returned ID token (issuer, audience, expiry,
nonce and signature via Google's JWKS) before trusting a single field.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError

from app.config import settings

logger = logging.getLogger(__name__)

GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
SCOPES = "openid email profile"
#: Discovery + JWKS documents change rarely; cache them for an hour.
CACHE_TTL_SECONDS = 3600
_HTTP_TIMEOUT = httpx.Timeout(10.0)


class OAuthError(Exception):
    """Raised for every failure of the OAuth exchange."""


@dataclass
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None
    hosted_domain: str | None


class _Cache:
    def __init__(self) -> None:
        self.discovery: dict[str, Any] | None = None
        self.discovery_at: float = 0.0
        self.jwks: Any = None
        self.jwks_at: float = 0.0

    def fresh(self, stamp: float) -> bool:
        return bool(stamp) and (time.time() - stamp) < CACHE_TTL_SECONDS


_cache = _Cache()


def _discovery() -> dict[str, Any]:
    if _cache.discovery and _cache.fresh(_cache.discovery_at):
        return _cache.discovery
    try:
        response = httpx.get(settings.google_discovery_url, timeout=_HTTP_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OAuthError("Nie udało się pobrać konfiguracji Google OAuth.") from exc
    _cache.discovery = response.json()
    _cache.discovery_at = time.time()
    return _cache.discovery


def _jwks():
    if _cache.jwks is not None and _cache.fresh(_cache.jwks_at):
        return _cache.jwks
    uri = _discovery().get("jwks_uri")
    if not uri:
        raise OAuthError("Konfiguracja Google nie zawiera jwks_uri.")
    try:
        response = httpx.get(uri, timeout=_HTTP_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OAuthError("Nie udało się pobrać kluczy Google (JWKS).") from exc
    _cache.jwks = JsonWebKey.import_key_set(response.json())
    _cache.jwks_at = time.time()
    return _cache.jwks


def authorization_url(state: str, nonce: str) -> str:
    """Build the URL the user is redirected to."""
    if not settings.oauth_configured:
        raise OAuthError(
            "Logowanie Google nie jest skonfigurowane. Ustaw GOOGLE_CLIENT_ID "
            "i GOOGLE_CLIENT_SECRET."
        )
    endpoint = _discovery().get("authorization_endpoint")
    if not endpoint:
        raise OAuthError("Konfiguracja Google nie zawiera authorization_endpoint.")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "access_type": "online",
        "prompt": "select_account",
    }
    if settings.google_allowed_domain:
        params["hd"] = settings.google_allowed_domain
    return f"{endpoint}?{urlencode(params)}"


def exchange_code(code: str) -> dict[str, Any]:
    """Swap the authorization code for tokens (server-to-server)."""
    endpoint = _discovery().get("token_endpoint")
    if not endpoint:
        raise OAuthError("Konfiguracja Google nie zawiera token_endpoint.")
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        response = httpx.post(endpoint, data=data, timeout=_HTTP_TIMEOUT)
    except httpx.HTTPError as exc:
        raise OAuthError("Nie udało się połączyć z serwerem tokenów Google.") from exc
    if response.status_code != 200:
        # Never log the payload: it contains the client secret and the code.
        logger.warning("Google token exchange failed with status %s", response.status_code)
        raise OAuthError("Google odrzucił kod autoryzacyjny.")
    payload = response.json()
    if "id_token" not in payload:
        raise OAuthError("Odpowiedź Google nie zawiera id_token.")
    return payload


def verify_id_token(id_token: str, expected_nonce: str) -> GoogleIdentity:
    """Validate signature, issuer, audience, expiry and nonce."""
    claims_options = {
        "iss": {"essential": True, "values": list(GOOGLE_ISSUERS)},
        "aud": {"essential": True, "values": [settings.google_client_id]},
        "exp": {"essential": True},
    }
    try:
        claims = JsonWebToken(["RS256"]).decode(
            id_token, key=_jwks(), claims_options=claims_options
        )
        claims.validate(leeway=60)
    except JoseError as exc:
        logger.warning("Google id_token rejected: %s", type(exc).__name__)
        raise OAuthError("Token tożsamości Google jest nieprawidłowy.") from exc

    if claims.get("nonce") != expected_nonce:
        raise OAuthError("Nieprawidłowy nonce - możliwa próba ataku replay.")

    email = claims.get("email")
    if not email:
        raise OAuthError("Konto Google nie udostępniło adresu e-mail.")
    if not claims.get("email_verified", False):
        raise OAuthError("Adres e-mail konta Google nie został zweryfikowany.")

    hosted_domain = claims.get("hd")
    if settings.google_allowed_domain and hosted_domain != settings.google_allowed_domain:
        raise OAuthError(
            f"Logowanie dozwolone tylko dla domeny {settings.google_allowed_domain}."
        )

    return GoogleIdentity(
        subject=str(claims["sub"]),
        email=str(email).lower(),
        email_verified=True,
        name=claims.get("name"),
        picture=claims.get("picture"),
        hosted_domain=hosted_domain,
    )
