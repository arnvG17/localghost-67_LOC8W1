# AwaazSetu WhatsApp Relay Service

A standalone FastAPI microservice that acts as a **WhatsApp relay bot** for the [AwaazSetu](https://awaazsetuapp.com) blue-collar job marketplace platform.

Uses **Twilio WhatsApp Sandbox** (FREE — no credit card, works in India). Shares **only a MongoDB Atlas database** with the main backend — no shared code, no inter-service API calls.

---

## What It Does

| Trigger | Action |
|---|---|
| New job inserted in MongoDB | Finds nearby workers (geo query), sends bilingual WhatsApp alerts |
| Worker replies **YES** | Assigns the job, notifies client, expires other sessions |
| Worker replies **NO** | Adds worker to `declined_workers`, next candidate auto-notified |
| Worker replies **INFO** | Sends detailed job description |
| Worker replies **SOS / HELP** | Creates an alert document for the emergency-response pipeline |
| Job status → `accepted` | Sends confirmation + chat/track links to the **client** |
| Job status → `completed` | Sends receipt link + rating prompt to **both** parties |
| Session expires (10 min TTL) | Marks expired, pushes worker to declined, triggers re-matching |

### Privacy Guarantees

- Worker phone numbers are **never** sent to clients.
- Client phone numbers are **never** sent to workers.
- All stored/logged phone references use **SHA-256 hashes**.
- Raw phone numbers are used **only** inside the Twilio API HTTP call and immediately discarded.

---

## Tech Stack

- Python 3.11+
- FastAPI (async)
- Motor (async MongoDB driver)
- **Twilio WhatsApp Sandbox** (FREE — no credit card needed)
- httpx (async HTTP)
- APScheduler (session expiry)
- python-dotenv

---

## Project Structure

```
awaazSetu-whatsapp/
├── main.py                 # FastAPI app, lifespan, scheduler
├── config.py               # Env vars, Motor client
├── requirements.txt
├── .env.example
├── Dockerfile
├── routers/
│   └── webhook.py          # POST /webhook/whatsapp (Twilio format)
├── services/
│   ├── matching.py         # Geospatial worker lookup
│   └── relay.py            # WhatsAppRelay (outbound via Twilio API)
├── streams/
│   └── job_watcher.py      # MongoDB change-stream listener
└── tasks/
    └── expiry.py           # Session expiry background task
```

---

## Twilio WhatsApp Sandbox Setup (FREE — India ✅)

### Step 1: Create a Twilio Account (2 minutes)

1. Go to **[twilio.com/try-twilio](https://www.twilio.com/try-twilio)** and sign up.
2. **No credit card needed** — the free trial includes sandbox access.
3. Verify your phone number (Twilio sends an SMS verification code).
4. When asked "What do you want to build?", select **WhatsApp** or skip.

### Step 2: Get Your Credentials

1. Go to the **[Twilio Console](https://console.twilio.com/)** (you land here after signup).
2. On the dashboard, you'll see:
   - **Account SID** → starts with `AC...` → this is your `TWILIO_ACCOUNT_SID`
   - **Auth Token** → click "Show" to reveal → this is your `TWILIO_AUTH_TOKEN`
3. Copy both into your `.env` file.

### Step 3: Activate the WhatsApp Sandbox

1. In the Twilio Console, go to **Messaging → Try it out → Send a WhatsApp message**.
   - Or go directly to: **[console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)**
2. You'll see a sandbox number: **+1 (415) 523-8886** (this is already in your `.env`).
3. **From your WhatsApp phone**, send the join code to this number:
   ```
   join <your-sandbox-code>
   ```
   Example: `join hungry-tiger` — send this as a WhatsApp message to **+14155238886**.
4. You'll get a reply: "You're connected to the sandbox!"

> **⚠️ Important:** Every WhatsApp number that needs to receive messages must send this join code first. This is a sandbox limitation.

### Step 4: Set Up the Webhook

1. In Twilio Console, go to **Messaging → Try it out → Send a WhatsApp message**.
2. Click on **Sandbox settings** (or go to **Messaging → Settings → WhatsApp sandbox settings**).
3. Set:
   | Field | Value |
   |---|---|
   | **When a message comes in** | `https://<your-ngrok-url>/webhook/whatsapp` |
   | **Method** | `POST` |
4. Click **Save**.

---

## Local Development

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Where to find it |
|---|---|
| `MONGO_URI` | Your MongoDB Atlas connection string |
| `TWILIO_ACCOUNT_SID` | Twilio Console dashboard (starts with `AC`) |
| `TWILIO_AUTH_TOKEN` | Twilio Console dashboard (click "Show") |
| `TWILIO_WHATSAPP_NUMBER` | Default: `+14155238886` (sandbox number) |
| `PHONE_HASH_SALT` | Any random secret string you choose |

### 3. Start the service

```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### 4. Expose via ngrok

```bash
ngrok http 8001
```

Copy the HTTPS URL (e.g. `https://a1b2c3d4.ngrok-free.app`).

### 5. Configure Twilio webhook

Paste `https://a1b2c3d4.ngrok-free.app/webhook/whatsapp` into Twilio's sandbox "When a message comes in" field.

### 6. Test it

1. Send a WhatsApp message to **+14155238886** (the sandbox number).
2. Check your server logs — you should see the message being received and processed.
3. Verify health:
```bash
curl http://localhost:8001/health
```

---

## Docker

```bash
docker build -t awaaz-whatsapp .
docker run --env-file .env -p 8001:8001 awaaz-whatsapp
```

---

## MongoDB Collections

| Collection | Access | Notes |
|---|---|---|
| `jobs` | Read + Write | Change-stream watch; updates `status`, `assigned_worker_id`, `declined_workers` |
| `workers` | Read | Geo-query for matching; reads `phone` internally only |
| `clients` | Read | Fetch client phone for outbound messages |
| `whatsapp_sessions` | Read + Write | **Created by this service** — tracks pending/accepted/declined/expired sessions |
| `alerts` | Write | SOS/HELP emergency alert documents |

### Required Index

```javascript
db.workers.createIndex({ location: "2dsphere" })
```

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service & MongoDB health check |
| `POST` | `/webhook/whatsapp` | Twilio inbound message webhook |

---

## Upgrading to Production (Meta WhatsApp Cloud API)

When your Meta Developer account is old enough, you can switch to Meta's official WhatsApp Cloud API for 1,000 free conversations/month. The only files that need changing are `config.py`, `services/relay.py`, and `routers/webhook.py`.
