"""
tasks/expiry.py — Expire stale whatsapp_sessions and push workers
to the job's declined_workers list so the change-stream can re-match.
"""

import logging
from datetime import datetime, timezone

from config import db

logger = logging.getLogger("awaaz.expiry")


async def expire_old_sessions() -> None:
    """
    Called every 2 minutes by APScheduler.

    1. Find all whatsapp_sessions where status == "pending"
       and expires_at < now.
    2. Mark each as "expired".
    3. Push the worker_id into jobs.declined_workers so the
       change-stream can notify the next candidate.
    """
    now = datetime.now(timezone.utc)

    try:
        cursor = db.whatsapp_sessions.find(
            {"status": "pending", "expires_at": {"$lt": now}}
        )
        expired_sessions = await cursor.to_list(length=500)

        if not expired_sessions:
            return

        logger.info("Expiring %d stale session(s)…", len(expired_sessions))

        for session in expired_sessions:
            try:
                # Mark session expired
                await db.whatsapp_sessions.update_one(
                    {"_id": session["_id"]},
                    {"$set": {"status": "expired"}},
                )

                # Push worker to declined_workers on the job
                await db.jobs.update_one(
                    {"_id": session["job_id"]},
                    {"$addToSet": {"declined_workers": session["worker_id"]}},
                )

                logger.info(
                    "Session %s expired — worker %s added to declined for job %s",
                    session["_id"],
                    session["worker_id"],
                    session["job_id"],
                )
            except Exception as exc:
                logger.error("Failed to expire session %s: %s", session["_id"], exc)

    except Exception as exc:
        logger.error("expire_old_sessions failed: %s", exc)
