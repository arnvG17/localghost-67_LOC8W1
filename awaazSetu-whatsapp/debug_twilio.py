import httpx
import os
from base64 import b64encode
from dotenv import load_dotenv

load_dotenv()

AC = os.getenv("TWILIO_ACCOUNT_SID")
TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM = os.getenv("TWILIO_WHATSAPP_NUMBER")
TO = "+919920704194" # Your phone

URL = f"https://api.twilio.com/2010-04-01/Accounts/{AC}/Messages.json"

payload = {
    "From": f"whatsapp:{FROM}",
    "To": f"whatsapp:{TO}",
    "Body": "Twilio Debug: Connecting to your phone!",
}

credentials = b64encode(f"{AC}:{TOKEN}".encode()).decode()
headers = {"Authorization": f"Basic {credentials}"}

print(f"Connecting to: {URL}")
print(f"From: {FROM} | To: {TO}")

try:
    # Try with verify=False first
    print("\n--- TEST 1: verify=False ---")
    with httpx.Client(verify=False) as client:
        resp = client.post(URL, data=payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

    # Try with verify=True
    print("\n--- TEST 2: verify=True ---")
    with httpx.Client() as client:
        resp = client.post(URL, data=payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

except Exception as e:
    print(f"\n❌ Error: {e}")
