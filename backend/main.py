from __future__ import annotations

import os


def _bootstrap_ssl_cert_file() -> None:
    """So OpenSSL finds CAs (helps python.org macOS); aiohttp/discord still use explicit context below."""
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        pass


_bootstrap_ssl_cert_file()

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Literal

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from backend.agent import run_agent
from backend.agent_runtime import (
    AgentConfigurationError,
    agent_ready,
    duffel,
    get_agent_graph,
    llm_provider_label,
)
from backend.booking import (
    CardPaymentDetails,
    OrderPassenger,
    ThreeDSChallengeError,
    create_instant_order,
)
from backend.llm_config import effective_llm_provider, llm_configured
from backend.config import settings
from backend.duffel_client import DuffelError
from backend.discord_bot import run_discord_bot
from backend.mailer import smtp_configured


def _log_discord_task_done(task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Discord bot task exited with an error — check token, intents, and network")


@asynccontextmanager
async def lifespan(app: FastAPI):
    discord_task: asyncio.Task[None] | None = None
    token = settings.discord_bot_token.strip()
    if token:
        discord_task = asyncio.create_task(run_discord_bot(token))
        discord_task.add_done_callback(_log_discord_task_done)
    yield
    if discord_task:
        discord_task.cancel()
        try:
            await discord_task
        except (asyncio.CancelledError, Exception):
            # Ignore failures during shutdown / reload (e.g. Discord SSL or cancelled login)
            pass


app = FastAPI(
    title="Airline flight-search agent",
    version="0.6.0",
    description="LangGraph ReAct agent with Duffel flight tools, instant orders (balance/card), optional Discord bot.",
    lifespan=lifespan,
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


class CreateOrderRequest(BaseModel):
    offer_id: str = Field(..., min_length=3, max_length=80)
    total_amount: str = Field(..., min_length=1, max_length=32, description="Exact total from the offer")
    total_currency: str = Field(..., min_length=3, max_length=3)
    passengers: list[OrderPassenger] = Field(..., min_length=1, max_length=9)
    payment_type: Literal["balance", "card"] = "balance"
    card: CardPaymentDetails | None = None

    @model_validator(mode="after")
    def _card_required_for_card_payment(self) -> CreateOrderRequest:
        if self.payment_type == "card" and self.card is None:
            raise ValueError("card is required when payment_type is 'card'")
        return self


class CreateOrderResponse(BaseModel):
    order_id: str
    booking_reference: str | None
    total_amount: str | None
    total_currency: str | None


@app.get("/api/health")
async def health():
    ds_reason = (settings.deepseek_reasoning_model or "").strip()
    ep = effective_llm_provider()
    return {
        "ok": True,
        "duffel_configured": duffel.configured(),
        "llm_configured": llm_configured(),
        "llm_provider": llm_provider_label(),
        "deepseek_reasoning_model": (ds_reason or None) if ep == "deepseek" else None,
        "discord_enabled": bool(settings.discord_bot_token.strip()),
        "agent_ready": agent_ready(),
        "agent_framework": "langgraph",
        "smtp_configured": smtp_configured(),
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    text = body.message.strip()
    hist = [{"role": m.role, "content": m.content} for m in body.history]

    try:
        graph = get_agent_graph()
    except AgentConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    reply = await run_agent(graph, hist, text)
    return ChatResponse(reply=reply)


@app.post("/api/orders", response_model=CreateOrderResponse)
async def create_order(body: CreateOrderRequest):
    """Create a Duffel instant order (test balance or card + 3DS when frictionless)."""
    if not duffel.configured():
        raise HTTPException(status_code=503, detail="Set DUFFEL_API_KEY to create orders.")
    try:
        raw = await create_instant_order(
            duffel,
            offer_id=body.offer_id,
            total_amount=body.total_amount,
            total_currency=body.total_currency,
            passengers=body.passengers,
            payment_mode=body.payment_type,
            card=body.card,
        )
    except ThreeDSChallengeError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "three_d_secure_challenge_required",
                "message": str(e),
                "client_id": e.client_id,
                "session_id": e.session_id,
            },
        ) from e
    except DuffelError as e:
        code = e.status_code or 502
        if code >= 500:
            raise HTTPException(status_code=502, detail=str(e)) from e
        raise HTTPException(status_code=400, detail=str(e)) from e

    data = raw.get("data") or {}
    oid = data.get("id")
    if not oid:
        raise HTTPException(status_code=502, detail="Duffel returned an order without an id.")
    return CreateOrderResponse(
        order_id=str(oid),
        booking_reference=data.get("booking_reference"),
        total_amount=data.get("total_amount"),
        total_currency=data.get("total_currency"),
    )
