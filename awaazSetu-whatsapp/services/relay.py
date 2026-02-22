"""
services/relay.py — One-way WhatsApp notifications via Twilio Sandbox.

When a notification is created in MongoDB:
  1. Look up user by user_id → get phone
  2. Look up job by job_id → get full details (address, time, pricing, etc.)
  3. Send a rich WhatsApp message to the user

No YES/NO flow — just confirmation/reminder messages.
"""

import hashlib
import logging
from base64 import b64encode

import httpx
from bson import ObjectId

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_NUMBER,
    PHONE_HASH_SALT,
    ADMIN_PHONE,
    db,
)

logger = logging.getLogger("awaaz.relay")

TWILIO_API_URL = (
    f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
)


class WhatsAppRelay:
    """Sends one-way WhatsApp notifications."""

    async def send_notification(
        self,
        user_id: str,
        job_id: str | None,
        notif_type: str,
        title: str,
        body: str,
    ) -> None:
        """
        Main entry point — look up user phone, look up job details,
        and send a WhatsApp message.
        """
        # ── 1. Find user → get phone ────────────────────────────────────
        try:
            user_oid = ObjectId(user_id)
        except Exception:
            logger.warning("Invalid user_id: %s", user_id)
            return

        user = await db.users.find_one({"_id": user_oid})
        if not user:
            logger.warning("User %s not found in apnakaam.users", user_id)
            return

        phone = user.get("phone", "")
        if not phone:
            logger.warning("User %s has no phone number", user_id)
            return

        user_name = user.get("name", "").strip()
        user_lang = user.get("preferred_language", "en")

        # ── 2. Find job → get details ───────────────────────────────────
        job = None
        if job_id:
            try:
                job_oid = ObjectId(job_id)
                job = await db.jobs.find_one({"_id": job_oid})
            except Exception as exc:
                logger.warning("Could not fetch job %s: %s", job_id, exc)

        # ── 3. Build and send message ───────────────────────────────────
        message = self._build_message(
            user_name=user_name,
            user_lang=user_lang,
            notif_type=notif_type,
            title=title,
            body=body,
            job=job,
        )

        # ── Send to user's actual phone ─────────────────────────────
        await self._send(phone, message)

        # ── Also send a copy to admin phone ──────────────────────────
        if ADMIN_PHONE and self._normalize(phone) != self._normalize(ADMIN_PHONE):
            await self._send(ADMIN_PHONE, f"[COPY — sent to {user_name or 'user'}]\n\n{message}")

    # ── Message builder ──────────────────────────────────────────────────

    def _build_message(
        self,
        user_name: str,
        user_lang: str,
        notif_type: str,
        title: str,
        body: str,
        job: dict | None,
    ) -> str:
        """Build a rich WhatsApp message with all job details."""

        # Greeting
        greeting = f"Hi {user_name}! 👋" if user_name else "Hello! 👋"

        # If we have job data, build a detailed message
        if job:
            service_type = job.get("service_type", "N/A")
            job_number = job.get("job_number", "")
            job_title = job.get("title", "")
            description = job.get("description", "")

            # Address
            address = job.get("address", {})
            full_address = address.get("full_address", "")
            city = address.get("city", "")
            pincode = address.get("pincode", "")
            location_str = ", ".join(filter(None, [full_address, city, pincode]))

            # Preferred time
            pref_time = job.get("preferred_time", {})
            date = pref_time.get("date", "")
            time_val = pref_time.get("time", "")
            time_str = f"{date} at {time_val}" if date and time_val else "ASAP"

            # Pricing
            pricing = job.get("pricing", {})
            estimated_amt = pricing.get("estimated_amount")
            price_range = pricing.get("price_range", {})
            if estimated_amt:
                pay_str = f"₹{estimated_amt}"
            elif price_range and price_range.get("min") and price_range.get("max"):
                pay_str = f"₹{price_range['min']}–₹{price_range['max']}"
            else:
                pay_str = "Negotiable"

            # Duration
            timeline = job.get("timeline", {})
            duration = timeline.get("estimated_duration_hours")
            duration_str = f"{duration} hours" if duration else "TBD"

            # Urgency
            urgency = job.get("urgency", "normal")
            urgency_icon = "🔴 Urgent" if urgency == "urgent" else "🟢 Normal"

            # Type-specific headers
            if notif_type == "job_accepted":
                header = "✅ *Worker Assigned — Job Confirmed!*"
            elif notif_type == "job_completed":
                header = "🎉 *Job Completed!*"
            elif notif_type == "job_started":
                header = "🚀 *Job Started!*"
            elif notif_type == "job_cancelled":
                header = "❌ *Job Cancelled*"
            else:
                header = f"🔔 *{title}*"

            msg = (
                f"{greeting}\n\n"
                f"{header}\n\n"
                f"📋 *{job_title or service_type.title()}*\n"
            )

            if job_number:
                msg += f"📄 Job #: {job_number}\n"
            if description:
                msg += f"📝 Details: {description}\n"

            msg += (
                f"\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📍 *Location:* {location_str}\n"
                f"🕐 *When:* {time_str}\n"
                f"💰 *Pay:* {pay_str}\n"
                f"⏱ *Duration:* {duration_str}\n"
                f"⚡ *Priority:* {urgency_icon}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
            )

            if notif_type == "job_accepted":
                msg += (
                    f"\nकृपया समय पर पहुँचें। | Please arrive on time.\n"
                    f"ऐप पर details देखें। | Check the app for full details."
                )
            elif notif_type == "job_completed":
                msg += f"\n⭐ कृपया अपना अनुभव रेट करें। | Please rate your experience."

            return msg

        else:
            # No job data — send the notification title/body as-is
            return (
                f"{greeting}\n\n"
                f"🔔 *{title}*\n\n"
                f"{body}"
            )

    # ── Twilio send ──────────────────────────────────────────────────────

    async def _send(self, phone: str, message: str) -> None:
        """POST message via Twilio WhatsApp API."""
        phone_hash = self._hash(phone)

        # Handle various phone formats: +919920704194, 9920704194, etc.
        clean = phone.replace(" ", "").replace("-", "")
        if clean.startswith("+91"):
            destination = clean
        elif clean.startswith("91") and len(clean) > 10:
            destination = f"+{clean}"
        elif len(clean) == 10:
            destination = f"+91{clean}"
        else:
            destination = f"+{clean}" if not clean.startswith("+") else clean

        payload = {
            "From": f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
            "To": f"whatsapp:{destination}",
            "Body": message,
        }

        credentials = b64encode(
            f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()
        ).decode()
        headers = {"Authorization": f"Basic {credentials}"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(TWILIO_API_URL, data=payload, headers=headers)
                if resp.status_code in (200, 201):
                    logger.info("✅ WhatsApp sent to [hash:%s…]", phone_hash[:12])
                else:
                    logger.warning(
                        "Twilio %s for [hash:%s…]: %s",
                        resp.status_code, phone_hash[:12], resp.text,
                    )
        except Exception as exc:
            logger.error("Twilio send failed for [hash:%s…]: %s", phone_hash[:12], exc)

    @staticmethod
    def _hash(phone: str) -> str:
        return hashlib.sha256(f"{PHONE_HASH_SALT}_{phone}".encode()).hexdigest()

    @staticmethod
    def _normalize(phone: str) -> str:
        """Strip to last 10 digits for comparison."""
        digits = "".join(c for c in phone if c.isdigit())
        return digits[-10:] if len(digits) >= 10 else digits


# Module-level singleton
relay = WhatsAppRelay()
