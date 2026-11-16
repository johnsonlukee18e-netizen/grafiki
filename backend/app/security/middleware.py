"""Security headers, CSRF double-submit check and a simple rate limiter."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import settings

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
#: Endpoints that legitimately arrive without a CSRF header.
CSRF_EXEMPT_PATHS = ("/api/auth/google", "/api/auth/google/callback", "/api/health")

CSP_API = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defence-in-depth headers (Nginx sets them for the SPA as well)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        headers.setdefault("Content-Security-Policy", CSP_API)
        headers.setdefault("Cache-Control", "no-store")
        if settings.is_production:
            headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie: the SPA echoes the CSRF cookie in a header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in SAFE_METHODS or request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)
        if request.cookies.get(settings.session_cookie_name) is None:
            # Unauthenticated request - the auth dependency will reject it.
            return await call_next(request)
        cookie_token = request.cookies.get(settings.csrf_cookie_name)
        header_token = request.headers.get("X-CSRF-Token")
        if not cookie_token or not header_token or cookie_token != header_token:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": "Nieprawidlowy token CSRF. Odswiez strone i sprobuj ponownie."
                },
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window counter per client IP.

    Good enough for a single-instance VPS deployment; Nginx adds its own
    limit_req zone in front of it.
    """

    #: How often idle counters are dropped (seconds).
    PRUNE_EVERY = 60.0

    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._last_prune = time.monotonic()

    def _prune(self, now: float, window: float) -> None:
        """Forget clients that have been quiet for a whole window.

        Without this every IP that ever called the API keeps a counter for the
        lifetime of the process - a slow memory leak on a public site.
        """
        if now - self._last_prune < self.PRUNE_EVERY:
            return
        self._last_prune = now
        stale = [key for key, hits in self._hits.items() if not hits or now - hits[-1] > window]
        for key in stale:
            del self._hits[key]

    def _bucket(self, path: str) -> tuple[str, int]:
        if path.startswith("/api/auth"):
            return "auth", settings.rate_limit_auth
        return "default", settings.rate_limit_default

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.rate_limit_enabled or request.method == "OPTIONS":
            return await call_next(request)
        bucket, limit = self._bucket(request.url.path)
        client = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client = forwarded.split(",")[0].strip()

        now = time.monotonic()
        window = settings.rate_limit_window_seconds
        self._prune(now, window)
        hits = self._hits[(client, bucket)]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            retry_after = int(window - (now - hits[0])) + 1
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Zbyt wiele zadan. Sprobuj ponownie za chwile."},
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
        return await call_next(request)
