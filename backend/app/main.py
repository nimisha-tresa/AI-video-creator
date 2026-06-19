from __future__ import annotations

import time

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import engine, init_db_schema
from app.models import *  # noqa: F401,F403 — ensure all models are imported for Alembic
from app.routers import assets, auth, generations, models, projects, ws
from app.routers import outputs
from app.routers.outputs import get_local_output

logger = structlog.get_logger()
settings = get_settings()

app = FastAPI(
    title="VideoCreator API",
    description="Higgsfield-grade AI video generation platform",
    version="1.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request timing middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    return response


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(models.router)
app.include_router(projects.router)
app.include_router(generations.router)
app.include_router(assets.router)
app.include_router(ws.router)
app.include_router(outputs.router)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}


# Top-level alias so generated output URLs (/local_outputs/{file}) resolve correctly.
app.add_api_route("/local_outputs/{filename}", get_local_output, methods=["GET"], tags=["outputs"])


@app.on_event("startup")
async def startup():
    logger.info("VideoCreator API starting", environment=settings.environment)
    should_create_schema = settings.db_auto_create_schema and (
        settings.environment != "production" or settings.db_auto_create_schema_in_production
    )
    if should_create_schema:
        await init_db_schema()
        logger.info("Database schema ensured")
    else:
        logger.info("Database schema auto-create skipped")


@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
    logger.info("VideoCreator API shut down")
