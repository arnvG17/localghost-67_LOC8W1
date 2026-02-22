"""
services/matching.py — Geospatial worker matching for incoming jobs.
"""

from config import db


async def find_nearby_workers(job: dict, max_distance: int = 5000, limit: int = 5) -> list:
    """
    Find up to *limit* nearby workers whose skill matches the job's
    service_type, are available, and have opted in to WhatsApp notifications.

    Uses MongoDB $nearSphere on workers.location (GeoJSON Point).
    max_distance is in metres (default 5 km).

    Returns full worker documents **including phone** (internal use only —
    phone is NEVER exposed in any API response).
    """
    try:
        cursor = db.workers.find(
            {
                "location": {
                    "$nearSphere": {
                        "$geometry": job["location"],
                        "$maxDistance": max_distance,
                    }
                },
                "skill": job.get("service_type"),
                "available": True,
                "whatsapp_opted_in": True,
            }
        ).limit(limit)

        workers = await cursor.to_list(length=limit)
        return workers
    except Exception as exc:
        import logging
        logging.getLogger("awaaz.matching").error("find_nearby_workers failed: %s", exc)
        return []
