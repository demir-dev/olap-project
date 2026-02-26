"""
FastAPI application entry point.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.dependencies import close_database, init_database
from app.orchestrator.session import evict_expired_sessions

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background task: session eviction
# ---------------------------------------------------------------------------

async def _session_eviction_loop() -> None:
    """Runs every 5 minutes to remove expired sessions."""
    while True:
        await asyncio.sleep(300)
        evict_expired_sessions()


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting OLAP BI Platform v%s", settings.app_version)
    init_database()
    eviction_task = asyncio.create_task(_session_eviction_loop())
    yield
    # Shutdown
    eviction_task.cancel()
    close_database()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OLAP BI Assistant API",
    description=(
        "A Multi-Agent Business Intelligence platform supporting Slice, Dice, "
        "Drill-Down, Roll-Up, Pivot, Compare, and Drill-Through OLAP operations "
        "on a Global Retail Sales star schema."
    ),
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS — allow frontend dev server and production origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Include API routes (no prefix — routes are /chat, /schema, /health)
app.include_router(router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "OLAP BI Assistant API",
        "docs": "/docs",
        "health": "/health",
    }
