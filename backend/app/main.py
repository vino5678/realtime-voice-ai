"""Voice Bridge API.

Phase 1: /api/health.  Phase 2: model status, voice enrollment, file-based conversion.
Real-time streaming is NOT implemented (Phase 3).
"""
from __future__ import annotations

import logging
import os
import platform
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.routes import router
from .config import Settings, load_settings
from .container import Container
from .errors import ApiError
from .services import create_engine
from .services.engine_base import VoiceEngine
from .services.jobs import JobManager
from .services.profiles import ProfileStore

APP_VERSION = "0.2.0"
_STARTED = time.monotonic()
log = logging.getLogger("voicebridge")


def create_app(settings: Settings | None = None, engine: VoiceEngine | None = None) -> FastAPI:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = settings or load_settings()
    engine = engine or create_engine(settings)
    profiles = ProfileStore(settings.profiles_dir)
    jobs = JobManager(settings, engine, profiles)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.ensure_dirs()
        jobs.cleanup_startup()
        engine.start_loading()
        log.info("startup version=%s engine=%s", APP_VERSION, settings.engine)
        yield
        jobs.shutdown()

    app = FastAPI(title="Voice Bridge API", version=APP_VERSION, lifespan=lifespan)
    app.state.vb = Container(settings, engine, profiles, jobs)

    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        body = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            body["details"] = exc.details
        return JSONResponse(status_code=exc.status, content={"error": body})

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in e.get("loc", ()) if p != "body") for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "The request is missing or has invalid fields.", "fields": fields}})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": str(exc.detail)}})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled_error")
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Something went wrong on the server."}})

    @app.get("/api/health")
    def health() -> dict:
        st = engine.status()
        return {
            "status": "ok",
            "service": "voice-bridge-api",
            "version": APP_VERSION,
            "time": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(time.monotonic() - _STARTED, 1),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "inference": {"available": st.state == "ready", "state": st.state, "note": st.reason},
        }

    app.include_router(router)
    return app


app = create_app()
