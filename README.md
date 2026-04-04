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

DISCORD_BOT_TOKEN=
DISCORD_COMMAND_PREFIX=!flight
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

Restart the server after you change `.env`.
