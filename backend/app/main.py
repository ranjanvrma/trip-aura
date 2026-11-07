"""TripAura FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import TripAuraError
from app.core.logging_config import configure_logging
from app.db.database import init_engine
from app.routers import location, meta, routes, trips

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("tripaura")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    log.info("TripAura started: DATA_MODE=%s, google_configured=%s, ai=%s",
             settings.data_mode.value, settings.google_configured, settings.ai_available)
    if settings.data_mode.value == "live" and not settings.google_configured:
        log.error("DATA_MODE=live but GOOGLE_MAPS_API_KEY is empty: itinerary requests will return 503.")
    yield


app = FastAPI(title="TripAura API", version="0.1.0", lifespan=lifespan,
              description="Personalised day-wise travel itineraries. Mock and Google Maps Platform data sources.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(TripAuraError)
async def tripaura_error(_: Request, exc: TripAuraError) -> JSONResponse:
    log.warning("%s: %s", exc.code, exc.message)
    return JSONResponse(status_code=exc.status_code,
                        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})


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


app.include_router(meta.router)
app.include_router(trips.router)
app.include_router(location.router)
app.include_router(routes.router)
