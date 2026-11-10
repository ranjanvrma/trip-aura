"""TripAura FastAPI application."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.errors import TripAuraError
from app.core.logging_config import configure_logging
from app.core.security import error_response, request_guard, security_headers
from app.db.database import init_engine
from app.routers import auth, geo, location, meta, nlp, routes, trips

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("tripaura")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.check_startup()   # e.g. APP_ENV=production without SECRET_KEY stops here
    init_engine()
    log.info("TripAura started: APP_ENV=%s, DATA_MODE=%s, google_configured=%s, ai=%s, email=%s",
             settings.app_env, settings.data_mode.value, settings.google_configured, settings.ai_available,
             "resend" if settings.email_configured else "dev log")
    if settings.data_mode.value == "live" and not settings.google_configured:
        log.error("DATA_MODE=live but GOOGLE_MAPS_API_KEY is empty: itinerary requests will return 503.")
    if settings.warmup_on_start:
        threading.Thread(target=_warm_up, name="warm-up", daemon=True).start()
    yield


def _warm_up() -> None:
    """Load the city index, embedding model and providers in the background at startup, so the
    first user request doesn't pay for them (a few seconds each)."""
    t = time.monotonic()
    try:
        from app.nlp.registry import get_city_index, get_semantic
        from app.routers.deps import get_itinerary_service

        get_city_index().load()
        _ = get_semantic().available
        get_itinerary_service()
        log.info("Warm-up finished in %.1fs", time.monotonic() - t)
    except Exception as exc:  # warm-up is an optimisation only
        log.warning("Warm-up skipped: %s", exc)


# Docs routes are registered below so DOCS_ENABLED is checked per request.
app = FastAPI(title="TripAura API", version="0.3.0", lifespan=lifespan, docs_url=None, redoc_url=None,
              openapi_url=None,
              description="Personalised day-wise travel itineraries for any city (open data, optional Google).")
# Middleware: the last one added runs first. Order of execution:
# security headers -> CORS (answers preflights) -> origin check + per-IP rate limit -> routes.
app.add_middleware(BaseHTTPMiddleware, dispatch=request_guard)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                   allow_origin_regex=settings.cors_origin_regex or None, allow_credentials=True,
                   allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                   allow_headers=["Content-Type", "X-CSRF-Token", "X-Idempotency-Key"],
                   expose_headers=["Retry-After", "Idempotent-Replayed"])
app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers)


@app.exception_handler(TripAuraError)
async def tripaura_error(_: Request, exc: TripAuraError) -> JSONResponse:
    log.warning("%s: %s", exc.code, exc.message)
    return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers or None)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    issues = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error",
                                                            "message": "Invalid trip details", "details": issues}})


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"error": {"code": "internal_error",
                                                            "message": "Unexpected server error"}})


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


def _docs_off() -> JSONResponse | None:
    if get_settings().docs_on:
        return None
    return error_response(404, "not_found", "Not found")


@app.get("/openapi.json", include_in_schema=False)
def openapi_schema():
    return _docs_off() or JSONResponse(app.openapi())


@app.get("/docs", include_in_schema=False)
def swagger_docs() -> HTMLResponse:
    return _docs_off() or get_swagger_ui_html(openapi_url="/openapi.json", title="TripAura API - docs")


@app.get("/redoc", include_in_schema=False)
def redoc_docs() -> HTMLResponse:
    return _docs_off() or get_redoc_html(openapi_url="/openapi.json", title="TripAura API - ReDoc")


app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(trips.router)
app.include_router(location.router)
app.include_router(routes.router)
app.include_router(geo.router)
app.include_router(nlp.router)
