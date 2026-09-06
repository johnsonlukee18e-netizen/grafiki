"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import (
    assignments,
    auth,
    availability,
    dashboard,
    employees,
    holidays,
    schedules,
    users,
)
from app.api import settings as settings_api
from app.config import settings
from app.database.session import engine
from app.security.middleware import (
    CSRFMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting nurse-scheduler API (env=%s)", settings.app_env)
    if settings.is_production and not settings.oauth_configured:
        logger.warning(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set - logging in will fail."
        )
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Nurse Scheduler API",
    description="Generowanie i zarzadzanie grafikami pracy pielegniarek i opiekunek.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

# Order matters: the outermost middleware is added last.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    max_age=600,
)

for router in (
    auth.router,
    dashboard.router,
    employees.router,
    availability.router,
    holidays.router,
    schedules.router,
    assignments.router,
    settings_api.router,
    users.router,
    users.audit_router,
):
    app.include_router(router)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness + database probe used by the Docker healthcheck."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - only hit when Postgres is down
        logger.exception("Database health check failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": "unavailable"},
        )
    return {"status": "ok", "database": "ok", "env": settings.app_env}


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Nieprawidlowe dane wejsciowe.",
            "errors": [
                {"field": ".".join(str(p) for p in error["loc"][1:]), "message": error["msg"]}
                for error in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak a stack trace to the browser; log it server-side instead."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    detail = "Wystapil nieoczekiwany blad serwera."
    if settings.debug:
        detail = f"{detail} ({type(exc).__name__}: {exc})"
    return JSONResponse(status_code=500, content={"detail": detail})
