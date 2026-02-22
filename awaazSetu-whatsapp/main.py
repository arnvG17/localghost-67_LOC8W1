"""
main.py — FastAPI entry-point for the AwaazSetu WhatsApp notification service.

Startup:
  • Launch MongoDB change-stream watcher on notifications collection (asyncio task)

Endpoints:
  GET  /health              — service & DB health check
  POST /webhook/whatsapp    — Twilio inbound webhook (optional — for future use)
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import db
from routers.webhook import router as webhook_router
from streams.job_watcher import watch_notifications

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("awaaz.main")


# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hook."""
    logger.info("🚀 AwaazSetu WhatsApp notification service starting…")

    # Background change-stream watcher on notifications collection
    watcher_task = asyncio.create_task(watch_notifications())

    yield  # ── app is running ──

    # Shutdown
    logger.info("Shutting down…")
    watcher_task.cancel()
    try:
        await watcher_task
    except asyncio.CancelledError:
        pass


# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AwaazSetu WhatsApp Notifications",
    version="2.0.0",
    description="WhatsApp notification bot for the AwaazSetu job marketplace.",
    lifespan=lifespan,
)

app.include_router(webhook_router)


# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Service health check — pings MongoDB (apnakaam database)."""
    try:
        await db.command("ping")
        mongo_status = "connected"
    except Exception as exc:
        mongo_status = f"error: {exc}"

    return {
        "service": "awaazSetu-whatsapp",
        "version": "2.0.0",
        "database": "apnakaam",
        "status": "running",
        "mongodb": mongo_status,
    }
