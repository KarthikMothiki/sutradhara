"""FastAPI application — Multi-Agent Task Management System.

This is the main entry point that:
- Initializes the database
- Mounts API routes and WebSocket endpoint
- Serves the Agent Trace UI
- Starts the scheduler for Tier 3 features
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    settings = get_settings()

    # ── Startup ─────────────────────────────────────────────
    logger.info("🚀 Starting Multi-Agent Task Management System…")
    logger.info(f"   Model chain: {settings.model_fallback_chain}")
    logger.info(f"   Database: {settings.database_url}")
    logger.info(f"   Scheduler: {'enabled' if settings.scheduler_enabled else 'disabled'}")

    # Initialize database
    from app.database.engine import init_db
    await init_db()
    logger.info("✅ Database initialized")

    # Start scheduler (Tier 3 features)
    from app.services.scheduler_service import setup_scheduler
    setup_scheduler()

    logger.info("✅ System ready — Sūtradhāra at your service! 🎭")

    yield

    # ── Shutdown ────────────────────────────────────────────
    logger.info("Shutting down…")

    from app.services.scheduler_service import shutdown_scheduler
    shutdown_scheduler()

    from app.database.engine import close_db
    await close_db()

    logger.info("👋 Goodbye!")


# ── App ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Multi-Agent Task Management System",
    description=(
        "A personal productivity orchestrator — AI agents that manage "
        "your Google Calendar and Notion tasks via natural language."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://KarthikMothiki.github.io"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount Routes ────────────────────────────────────────────────

from app.api.routes import router as api_router
from app.api.websocket import router as ws_router

app.include_router(api_router)
app.include_router(ws_router)


# ── Mount Frontend ──────────────────────────────────────────────

frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    logger.info(f"📂 Frontend mounted from {frontend_path}")


# ── Health Check ────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {
        "status": "healthy",
        "service": "multi-agent-task-system",
        "version": "1.0.0",
    }


# ── Run directly ────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level,
    )
