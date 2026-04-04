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
from pydantic import BaseModel, Field

from backend.agent import run_agent
from backend.agent_runtime import (
    AgentConfigurationError,
    agent_ready,
    duffel,
    get_agent_graph,
    llm_provider_label,
)
from backend.llm_config import llm_configured
from backend.config import settings
from backend.discord_bot import run_discord_bot


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
    version="0.3.0",
    description="LangGraph ReAct agent with Duffel flight tools; optional Discord bot.",
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


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "duffel_configured": duffel.configured(),
        "llm_configured": llm_configured(),
        "llm_provider": llm_provider_label(),
        "discord_enabled": bool(settings.discord_bot_token.strip()),
        "agent_ready": agent_ready(),
        "agent_framework": "langgraph",
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
