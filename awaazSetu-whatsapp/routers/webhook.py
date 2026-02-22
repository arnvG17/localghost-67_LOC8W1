"""
routers/webhook.py — Twilio WhatsApp inbound-message webhook.

POST /webhook/whatsapp — Twilio sends form-encoded data on incoming messages.
Handles YES/NO/INFO/SOS replies from workers.

Always returns 200 OK with empty TwiML to prevent Twilio retries.
"""

import hashlib
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Request, Response

from config import PHONE_HASH_SALT, db
from services.relay import relay

router = APIRouter()
logger = logging.getLogger("awaaz.webhook")

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _hash(phone: str) -> str:
    return hashlib.sha256(f"{PHONE_HASH_SALT}_{phone}".encode()).hexdigest()


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request) -> Response:
    """Process inbound WhatsApp messages from Twilio."""
    try:
        form = await request.form()
    except Exception:
        logger.warning("Could not parse webhook body")
        return Response(content=EMPTY_TWIML, media_type="application/xml", status_code=200)

    try:
        await _process_twilio_message(dict(form))
    except Exception as exc:
        logger.error("Webhook processing error: %s", exc)

    return Response(content=EMPTY_TWIML, media_type="application/xml", status_code=200)


async def _process_twilio_message(form: dict) -> None:
    """Parse Twilio form data and dispatch."""
    raw_from = form.get("From", "")
    body = form.get("Body", "")

    # Strip "whatsapp:" prefix and country code
    raw_phone = raw_from.replace("whatsapp:", "").strip()
    if raw_phone.startswith("+91"):
        raw_phone = raw_phone[3:]
    elif raw_phone.startswith("91") and len(raw_phone) > 10:
        raw_phone = raw_phone[2:]
    elif raw_phone.startswith("+"):
        raw_phone = raw_phone[1:]

    text = body.strip().upper()
    if not raw_phone or not text:
        return

    await _handle_message(raw_phone, text)


async def _handle_message(raw_phone: str, text: str) -> None:
    """Hash phone, find active session, dispatch by keyword."""
    phone_hash = _hash(raw_phone)
    now = datetime.now(timezone.utc)

    # Find active (pending) session for this phone
    session = await db.whatsapp_sessions.find_one({
        "phone_hash": phone_hash,
        "status": "pending",
        "expires_at": {"$gt": now},
    })

    if not session:
        await relay._send(
            raw_phone,
            "❌ कोई active job नहीं। | No active job found.\n\n"
            "जब कोई नया काम आएगा, हम आपको बताएँगे।\n"
            "We'll notify you when a new job is available."
        )
        return

    job_id = session["job_id"]
    worker_id = session["worker_id"]
    job_number = session.get("job_number", "")

    if text in ("YES", "हाँ", "HA", "HAAN", "Y"):
        await _handle_accept(raw_phone, session, job_id, worker_id, job_number)
    elif text in ("NO", "नहीं", "NAHI", "N"):
        await _handle_decline(raw_phone, session, job_id, worker_id, job_number)
    elif text == "INFO":
        await _handle_info(raw_phone, job_id)
    elif text in ("SOS", "HELP"):
        await _handle_sos(raw_phone, session, job_id, worker_id)
    else:
        await relay._send(
            raw_phone,
            "❓ *Valid commands | मान्य कमांड:*\n\n"
            "✅ *YES* — Accept job | काम स्वीकार करें\n"
            "❌ *NO* — Decline job | मना करें\n"
            "ℹ️ *INFO* — Job details | काम की जानकारी\n"
            "🆘 *SOS* — Emergency help | आपातकालीन सहायता"
        )


async def _handle_accept(raw_phone, session, job_id, worker_id, job_number):
    """Worker accepted the job."""
    now = datetime.now(timezone.utc)

    # Convert to ObjectId if string
    job_oid = ObjectId(job_id) if isinstance(job_id, str) else job_id

    # Update job — set status to accepted and assign worker
    await db.jobs.update_one(
        {"_id": job_oid},
        {
            "$set": {
                "status": "accepted",
                "worker_id": worker_id,
                "timeline.matched_at": now,
                "updated_at": now,
            }
        },
    )

    # Mark session accepted
    await db.whatsapp_sessions.update_one(
        {"_id": session["_id"]},
        {"$set": {"status": "accepted"}},
    )

    # Expire all other pending sessions for same job
    await db.whatsapp_sessions.update_many(
        {"job_id": job_id, "status": "pending", "_id": {"$ne": session["_id"]}},
        {"$set": {"status": "expired"}},
    )

    await relay._send(
        raw_phone,
        f"✅ *काम confirm! | Job Confirmed!* 🎉\n\n"
        f"Job #{job_number} आपको assign हो गया है।\n"
        f"Job #{job_number} has been assigned to you.\n\n"
        f"Client ऐप पर आपसे संपर्क करेगा।\n"
        f"The client will contact you via the app."
    )
    logger.info("Worker %s accepted job %s", worker_id, job_number)


async def _handle_decline(raw_phone, session, job_id, worker_id, job_number):
    """Worker declined the job."""
    job_oid = ObjectId(job_id) if isinstance(job_id, str) else job_id

    # Add to declined workers list
    await db.jobs.update_one(
        {"_id": job_oid},
        {
            "$addToSet": {"matching.workers_declined": worker_id},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )

    # Mark session declined
    await db.whatsapp_sessions.update_one(
        {"_id": session["_id"]},
        {"$set": {"status": "declined"}},
    )

    await relay._send(
        raw_phone,
        f"❌ आपने काम #{job_number} मना किया। | You declined job #{job_number}.\n\n"
        f"अगला काम मिलने पर हम आपको बताएँगे।\n"
        f"We'll notify you when the next job is available."
    )
    logger.info("Worker %s declined job %s", worker_id, job_number)


async def _handle_info(raw_phone, job_id):
    """Send full job details."""
    job_oid = ObjectId(job_id) if isinstance(job_id, str) else job_id
    job = await db.jobs.find_one({"_id": job_oid})

    if not job:
        await relay._send(raw_phone, "Job details not found.")
        return

    # Build detailed info from real schema
    service = job.get("service_type", "N/A")
    title = job.get("title", "")
    desc = job.get("description", "N/A")

    address = job.get("address", {})
    location = f"{address.get('full_address', '')}, {address.get('city', '')} {address.get('pincode', '')}".strip(", ")

    pref = job.get("preferred_time", {})
    time_str = f"{pref.get('date', '')} {pref.get('time', '')}".strip() or "ASAP"

    pricing = job.get("pricing", {})
    est = pricing.get("estimated_amount")
    pr = pricing.get("price_range", {})
    if est:
        pay = f"₹{est}"
    elif pr.get("min") and pr.get("max"):
        pay = f"₹{pr['min']}–₹{pr['max']}"
    else:
        pay = "Negotiable"

    duration = job.get("timeline", {}).get("estimated_duration_hours", "TBD")
    urgency = job.get("urgency", "normal")
    job_number = job.get("job_number", "")

    await relay._send(
        raw_phone,
        f"📋 *Job Details — #{job_number}*\n\n"
        f"📌 *{title}*\n"
        f"🔹 Type: {service.title()}\n"
        f"📝 Description: {desc}\n"
        f"📍 Location: {location}\n"
        f"🕐 When: {time_str}\n"
        f"💰 Pay: {pay}\n"
        f"⏱ Duration: {duration} hrs\n"
        f"⚡ Urgency: {urgency.title()}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Reply *YES* to accept | *NO* to decline"
    )


async def _handle_sos(raw_phone, session, job_id, worker_id):
    """Emergency SOS."""
    try:
        await db.alerts.insert_one({
            "type": "whatsapp_sos",
            "worker_id": worker_id,
            "job_id": job_id,
            "triggered_at": datetime.now(timezone.utc),
            "channel": "whatsapp",
        })
    except Exception as exc:
        logger.error("Failed to insert SOS alert: %s", exc)

    await relay._send(
        raw_phone,
        "🆘 *मदद आ रही है! | Help is on the way!*\n\n"
        "हमारी टीम को सूचित कर दिया गया है।\n"
        "Our team has been notified and will assist you shortly."
    )
    logger.info("SOS triggered by worker %s for job %s", worker_id, job_id)
