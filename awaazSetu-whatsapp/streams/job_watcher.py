"""
streams/job_watcher.py — MongoDB change-stream on `notifications` collection.

Watches for NEW notifications being inserted into apnakaam.notifications.
When a notification is created (e.g. type=job_accepted):
  1. Look up the user by user_id → get their phone
  2. Look up the job by data.job_id → get location, time, service details
  3. Send a one-way WhatsApp confirmation message to the user
"""

import asyncio
import logging

from config import db
from services.relay import relay

logger = logging.getLogger("awaaz.watcher")

MAX_RETRIES = 5


async def watch_notifications() -> None:
    """Watch the notifications collection for new inserts."""
    retries = 0
    backoff = 1

    while retries < MAX_RETRIES:
        try:
            logger.info("Starting notifications change-stream (attempt %d)…", retries + 1)

            pipeline = [
                {"$match": {"operationType": "insert"}}
            ]

            async with db.notifications.watch(
                pipeline, full_document="updateLookup"
            ) as stream:
                retries = 0
                backoff = 1
                logger.info("✅ Change-stream connected — watching for new notifications")

                async for change in stream:
                    try:
                        doc = change.get("fullDocument")
                        if doc:
                            await _handle_notification(doc)
                    except Exception as exc:
                        logger.error("Error handling notification: %s", exc)

        except Exception as exc:
            retries += 1
            logger.warning(
                "Change-stream disconnected (%s). Retry %d/%d in %ds…",
                exc, retries, MAX_RETRIES, backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    logger.error("Change-stream gave up after %d retries.", MAX_RETRIES)


async def _handle_notification(notification: dict) -> None:
    """Process a new notification and send WhatsApp message."""
    notif_type = notification.get("type", "")
    user_id = notification.get("user_id")
    data = notification.get("data", {})
    job_id = data.get("job_id")
    title = notification.get("title", "")
    body = notification.get("body", "")

    logger.info(
        "New notification: type=%s, user=%s, job=%s, title=%s",
        notif_type, user_id, job_id, title,
    )

    # Send WhatsApp for any notification that has a user_id
    if user_id:
        await relay.send_notification(
            user_id=user_id,
            job_id=job_id,
            notif_type=notif_type,
            title=title,
            body=body,
        )
