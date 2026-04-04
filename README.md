# AI flight-search agent (interview assignment)

This repo implements a **functioning AI agent** for a real problem (finding airline options): a **LangGraph** ReAct-style agent with **LLM + tools**, aligned with a “code first” stack (e.g. LangChain / **LangGraph**, Pydantic).

**Flights:** **[Duffel](https://duffel.com/)** Flights API — sign up at **[app.duffel.com/join](https://app.duffel.com/join)**, create a **test access token** (`duffel_test_…`) under Developers → Access tokens, and set `DUFFEL_API_KEY`. [Test mode](https://duffel.com/docs/api/overview/test-mode) returns sandbox offers (no real bookings). See the [getting started guide](https://duffel.com/docs/guides/getting-started-with-flights).

We **do not use Amadeus** (self-service access is limited) or **Kiwi Tequila** (Tequila is [partner-restricted / not open for general signup](https://tequila.kiwi.com/portal/docs/tequila_api)). Duffel is a practical developer-first alternative with clear docs and a sandbox.

**LLM:** Prefer **[DeepSeek](https://www.deepseek.com/)** via LangChain **`ChatDeepSeek`**. Set `DEEPSEEK_API_KEY`. With `LLM_PROVIDER=auto`, DeepSeek wins if that key is set, else **OpenAI**.

**Important:** Use **`deepseek-chat`** for tool calling. **`deepseek-reasoner`** (R1-style) does **not** support tool calling in the API.

## What to show in the interview

- **Problem:** Trip planning / fare discovery is fragmented; an agent combines natural language with structured flight search.
- **Architecture:** FastAPI → **LangGraph** `create_react_agent` → **ChatDeepSeek** or **ChatOpenAI** → tools (`lookup_iata`, `search_flight_offers`) → **Duffel** → summarized reply (optional **Discord**).
- **Why Duffel over Kiwi:** Tequila/Kiwi API access is gated for many developers; Duffel’s test tokens and docs are built for integration work.

## Setup

1. **Duffel:** [Join](https://app.duffel.com/join) → Dashboard → **Developers** → **Access tokens** → create token → `DUFFEL_API_KEY` in `.env`.
2. **LLM:** `DEEPSEEK_API_KEY` and/or `OPENAI_API_KEY`.
3. Copy `.env.example` → `.env` and fill values.

```bash
cd /path/to/AI-Chatbot-Airlines-Booking
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

**`python run.py`** starts uvicorn with **`--loop asyncio`** (not uvloop). On **macOS**, the default **uvloop** loop often causes **`SSL: CERTIFICATE_VERIFY_FAILED`** for Discord’s aiohttp client, so the bot never connects and appears offline.

Equivalent manual command:

`uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 --loop asyncio`

If TLS still fails, run **`/Applications/Python 3.12/Install Certificates.command`** once (python.org install).

Use **Discord** (below), **curl**, or **http://127.0.0.1:8000/docs** for `/api/chat`.

## Discord (optional)

With `DISCORD_BOT_TOKEN` in `.env`, uvicorn starts the Discord client. Same agent as `/api/chat`.

1. [Discord Developer Portal](https://discord.com/developers/applications) → **Bot** → token → `DISCORD_BOT_TOKEN`.
2. Enable **Message Content Intent** on the bot.
3. OAuth2 URL with **bot** scope; invite to a server.
4. In a channel: `!flight Paris to Berlin on 2026-08-12` or @mention the bot. DMs need no prefix.

**Bot does nothing in a server?**

- **Keep uvicorn running** — the Discord connection lives in the same process. If you stop the terminal, the bot goes **offline** and will not answer.
- **Message Content Intent** — In the Developer Portal → your app → **Bot** → **Privileged Gateway Intents**, turn **Message Content Intent** **ON**, then **Save**. Without it, Discord does **not** send message text to the bot in servers, so `!flight …` is invisible and the code never replies.
- Confirm the bot appears **online** (green) in the member list. If it’s offline, check the terminal for errors (bad token, task crash).
- **Channel permissions:** the bot needs **View Channel** + **Send Messages** in that channel.
- **`SSL: CERTIFICATE_VERIFY_FAILED` for Discord:** the app pins TLS for Discord via **`truststore`** (macOS) / **certifi**. Run `pip install -r requirements.txt`. If it still fails: **Install Certificates.command** in `/Applications/Python 3.x/`, or **`uvicorn ... --loop asyncio`**.

## API

- `GET /api/health` — `duffel_configured`, `llm_configured`, `llm_provider`, `discord_enabled`, `agent_ready`, `agent_framework`
- `POST /api/chat` — `{ "message": "...", "history": [] }` → `{ "reply": "..." }`

## Files

Hand-written layout (**15** repo files + optional local **`.env`**). After you run the app, `backend/__pycache__/` adds `.pyc` bytecode — many editors then show **~23** files total (source + cache + `.env`).

```
.
├── .env.example          # copy → .env
├── .gitignore
├── README.md
├── requirements.txt
├── run.py                # uvicorn with asyncio loop (Discord on macOS)
└── backend/
    ├── __init__.py
    ├── agent.py          # LangGraph agent + Duffel tools
    ├── agent_runtime.py  # Duffel client + compiled graph
    ├── config.py         # pydantic-settings / .env
    ├── discord_bot.py    # Discord adapter (aiohttp TLS)
    ├── duffel_client.py  # place suggestions + offer requests
    ├── flight_format.py  # format Duffel offers for chat
    ├── llm_config.py
    ├── llm_factory.py    # ChatDeepSeek vs ChatOpenAI
    └── main.py           # FastAPI + lifespan
```
