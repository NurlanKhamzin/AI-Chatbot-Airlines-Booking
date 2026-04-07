# Flight search assistant

A small web API that answers in plain English when you ask for flights. It looks up airports and prices through the [Duffel](https://duffel.com/) API and uses an AI model (DeepSeek or OpenAI) to talk to you. You can use it from the built-in docs page, from any HTTP client, or from Discord if you add a bot token.

At first the idea was to use **Amadeus** for real airline data, but their API isn’t realistically available to independent developers anymore (self-service access is very limited), so the app uses **Duffel** instead, which is built for this kind of integration and works well with a test token.

---

## What you need before you start

1. **Duffel** — Free to sign up. In the dashboard go to Developers → Access tokens and create a **test** token (it starts with `duffel_test_`). That lets you search fake inventory without buying real tickets.

2. **An LLM API key** — Either **DeepSeek** or **OpenAI**. If you set both, the app prefers DeepSeek when `LLM_PROVIDER` is `auto`.

---

## Configuration

Create a file named `.env` in the project root (same folder as `run.py`). You can copy the block below and fill in your values.

```
DUFFEL_API_KEY=your_duffel_test_token

LLM_PROVIDER=auto
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_REASONING_MODEL=deepseek-reasoner

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=

# Optional: frictionless 3DS in dev only (see Duffel corporate / 3DS docs). Leave empty in production.
DUFFEL_THREE_DS_EXCEPTION=

DISCORD_BOT_TOKEN=
DISCORD_COMMAND_PREFIX=!flight

# Optional: itinerary email — local dev with Mailpit (run `mailpit`, UI http://127.0.0.1:8025)
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_FROM=bookings@local.test
SMTP_USER=
SMTP_PASSWORD=
SMTP_USE_TLS=0
SMTP_SSL=0
```

- **`DEEPSEEK_REASONING_MODEL`** — Optional. If set (e.g. to `deepseek-reasoner`), the app runs a second pass to polish the answer. Leave it empty if you want one call only and lower cost.
- **Discord** — Leave `DISCORD_BOT_TOKEN` empty if you only use the web API. To use the bot, create an application in the [Discord developer portal](https://discord.com/developers/applications), copy the bot token, turn on **Message Content Intent**, and invite the bot to your server with message permissions.
- In a **server channel**, the bot usually expects messages that start with **`!flight`** (or whatever you set) or an **@mention**. In **DMs** you can write normally.

---

## Run locally

```bash
cd AI-Chatbot-Airlines-Booking
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The API listens at **http://127.0.0.1:8000**. Open **http://127.0.0.1:8000/docs** to try `POST /api/chat` from the browser.

On a Mac, if the Discord bot fails to connect with an SSL error, start the server with the asyncio loop (the `run.py` script already does this), or run:

`uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 --loop asyncio`

If problems persist, run **Install Certificates.command** from your Python folder (for python.org installs).

---

## Using the API

- **Health check:** `GET /api/health` — shows whether Duffel, the LLM, and the agent are configured.
- **Chat:** `POST /api/chat` with JSON like:

```json
{
  "message": "Flights from Paris to Berlin on 2026-08-12, one adult",
  "history": []
}
```

The response is `{ "reply": "..." }`. You can add past turns to `history` if you want continuity.

**Booking in chat (same for Discord):** If the user asks to book an offer, the model is instructed to collect **traveler + passport** details first, then **payment**. With a **test** Duffel token, **`payment_type=balance`** completes the booking **without any card** (prefer this for demos). **Card** data is only used to call **`book_flight_offer`** (Duffel’s card API)—never to email card numbers to a personal inbox; **itinerary email** is only for the confirmation message after booking. Some LLMs may still refuse to type card fields; use **balance** or a different model if that happens. If **`SMTP_HOST`** and **`SMTP_FROM`** are set, the server emails a plain-text itinerary. **`GET /api/health`** includes **`smtp_configured`**.

- **Instant order (test):** `POST /api/orders` — book a single offer with Duffel test **balance** or a **card** (see OpenAPI at `/docs`). Use the **offer id** (`off_…`) and **passenger ids** (`pas_…`) shown in the chat after a search. `total_amount` and `total_currency` must match the offer exactly.

Sending raw card numbers to your own server has **PCI** implications; for production, Duffel recommends **Duffel Components** so card data goes straight to Duffel. If 3DS returns `challenge_required`, the API responds with **409** and a `client_id` for a browser challenge (or use a frictionless test card from Duffel’s docs, or the optional `DUFFEL_THREE_DS_EXCEPTION` only where appropriate).

---

## Tests

```bash
pip install -r requirements.txt
pytest
```

Checks include offer formatting (ids visible for booking), booking flow with mocked Duffel, and **response-quality** helpers that flag when a reply drops tool-sourced prices (plus a mocked “reasoning” pass that must keep amounts).

Restart the server after you change `.env`.

---

## Itinerary email after booking (Mailpit — local dev)

The app sends itinerary mail to whatever SMTP you configure. For **local testing**, use **[Mailpit](https://github.com/axllent/mailpit)** (nothing is delivered to the real internet; you read messages in a browser).

1. Install and start Mailpit, e.g. run `mailpit` in a terminal, or:  
   `docker run -d --rm -p 8025:8025 -p 1025:1025 axllent/mailpit`
2. Keep `.env` aligned with the sample project (already set for Mailpit): `SMTP_HOST=127.0.0.1`, `SMTP_PORT=1025`, `SMTP_FROM=...`, `SMTP_USE_TLS=0`, `SMTP_SSL=0`, empty user/password.
3. Restart `python run.py`, then check **`GET /api/health`** → **`smtp_configured`: true**.
4. After a booking, open **http://127.0.0.1:8025** to see the itinerary message.

If **`smtp_configured`** is false, the booking still succeeds in Duffel but no email is sent.
