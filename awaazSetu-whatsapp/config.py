"""
config.py — Environment variables & Motor (async MongoDB) client initialisation.
"""

import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

# ── MongoDB ──────────────────────────────────────────────────────────────────
MONGO_URI: str = os.getenv("MONGO_URI", "")
_client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)

# Main database — apnakaam (notifications, users, jobs)
db = _client["apnakaam"]

# ── Twilio WhatsApp Sandbox (FREE) ───────────────────────────────────────────
TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "+14155238886")

# ── Admin — always gets a copy of every notification ─────────────────────────
ADMIN_PHONE: str = os.getenv("ADMIN_PHONE", "+919920704194")

# ── Privacy ──────────────────────────────────────────────────────────────────
PHONE_HASH_SALT: str = os.getenv("PHONE_HASH_SALT", "change_this_to_random_secret")
