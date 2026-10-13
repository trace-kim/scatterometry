"""Application factory: API under /api, the built web UI (web/dist) at /."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from typing import Optional

import anyio.to_thread
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .arrays import NPZ_MEDIA_TYPE
from .events import EventBroker
from .jobs import JobManager
from .routes import dielectric, events, geometry, projects, python_views, runs, sweeps
from .settings import Settings

log = logging.getLogger("maskserver")

try:
    __version__ = version("maskserver")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"


def limit_blas_threads(threads: int):
    """Cap BLAS threads (call after NumPy is imported); returns the threadpoolctl handle or None."""
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:
        return None
    return threadpool_limits(limits=threads, user_api="blas")


class BodySizeLimit:
    """Refuse request bodies over `max_bytes` with HTTP 413 before they are buffered in memory."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await JSONResponse({"detail": "request body too large"}, status_code=413)(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:  # chunked uploads declare no length
                    # FastAPI re-raises HTTPExceptions from body reading as responses.
                    raise HTTPException(status_code=413, detail="request body too large")
            return message

        await self.app(scope, limited_receive, send)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings()
    broker = EventBroker()
    jobs = JobManager(broker, max_workers=settings.max_jobs, keep=settings.keep_results,
                      keep_bytes=int(settings.max_results_gb * 2**30))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.blas_limit = limit_blas_threads(settings.blas_threads)
        # Sync endpoints run on AnyIO's thread pool (40 threads by default). Fewer threads
        # cap how many large views are computed at once; further requests wait their turn.
        anyio.to_thread.current_default_thread_limiter().total_tokens = settings.request_threads
        broker.bind(asyncio.get_running_loop())
        yield
        jobs.shutdown()

    app = FastAPI(
        title="RCWA mask simulator API",
        version=__version__,
        description="Photomask RCWA solves, geometry and field views. Lengths in nm, angles in degrees.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.jobs = jobs
    app.state.broker = broker

    # Compress JSON only. Float arrays barely shrink (~10%) but cost ~50-150 ms of CPU per
    # field plane, and the event stream must never be buffered.
    app.add_middleware(GZipMiddleware, minimum_size=4096, compresslevel=5,
                       exclude_content_types=DEFAULT_EXCLUDED_CONTENT_TYPES + (NPZ_MEDIA_TYPE,))
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                           allow_headers=["*"])
    app.add_middleware(BodySizeLimit, max_bytes=int(settings.max_body_mb * 2**20))  # added last: outermost

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__, "blas_threads": settings.blas_threads,
                "max_jobs": settings.max_jobs}

    for module in (projects, geometry, dielectric, runs, sweeps, events, python_views):
        api.include_router(module.router)
    app.include_router(api)

    if settings.serves_web:
        app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
    else:
        log.info("web UI not built (%s); serving the API only", settings.web_dist)
    return app
