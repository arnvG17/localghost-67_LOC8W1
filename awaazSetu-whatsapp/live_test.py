"""Live Test: Sends a notification to 'Arnav (Test)' (+919920704194)."""
import asyncio, os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def main():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
    db = client["apnakaam"]

    # Target the user 'Arnav (Test)'
    user = await db.users.find_one({"phone": "+919920704194"})
    if not user:
        print("User '+919920704194' not found in users collection. Please check inspect_db.py output.")
        return

    user_id = str(user["_id"])
    print(f"Target User: {user.get('name')} | {user.get('phone')} (ID: {user_id})")

    # Get a real job to pull data from
    job = await db.jobs.find_one(sort=[("created_at", -1)])
    if not job:
        print("No jobs found to reference.")
        return

    job_id = str(job["_id"])
    print(f"Referencing Job: {job.get('job_number')} — {job.get('title')}")

    # Insert notification
    notification = {
        "user_id": user_id,
        "type": "new_job_alert",
        "title": "Final Test Notification! 🛠️",
        "body": f"Hi {user.get('name')}, this is a live test of your WhatsApp notification service!",
        "data": {"job_id": job_id},
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }

    print(f"\n📨 Inserting live test notification...")
    await db.notifications.insert_one(notification)
    print("✅ Done! You should receive the WhatsApp message on your phone momentarily.")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
