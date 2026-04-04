"""Discord adapter: forwards eligible messages to the same LangGraph agent as /api/chat."""

from __future__ import annotations

import asyncio
import logging
import re
import ssl
import sys
from collections import defaultdict, deque

import aiohttp
import certifi
import discord

from backend.agent import run_agent
from backend.agent_runtime import AgentConfigurationError, get_agent_graph
from backend.config import settings

logger = logging.getLogger(__name__)

MAX_STORED_MESSAGES = 24
_history: dict[str, deque[dict[str, str]]] = defaultdict(
    lambda: deque(maxlen=MAX_STORED_MESSAGES)
)


def _command_prefix() -> str:
    return (settings.discord_command_prefix or "!flight").strip()


def _conversation_key(message: discord.Message) -> str:
    if message.guild is None:
        return f"dm:{message.author.id}"
    return f"guild:{message.guild.id}:ch:{message.channel.id}:user:{message.author.id}"


def _strip_query(content: str, message: discord.Message) -> str:
    text = content.strip()
    for mention in message.mentions:
        text = text.replace(mention.mention, " ")
    text = re.sub(r"<@!?\d+>", " ", text)
    text = text.strip()
    prefix = _command_prefix()
    if message.guild and text.lower().startswith(prefix.lower()):
        text = text[len(prefix) :].strip()
    return text


def _should_respond(message: discord.Message, client: discord.Client) -> bool:
    if message.author.bot:
        return False
    raw = (message.content or "").strip()
    if not raw:
        return False
    if message.guild is None:
        return True
    if client.user and client.user in message.mentions:
        return True
    return raw.lower().startswith(_command_prefix().lower())


def _chunk_discord(text: str, limit: int = 1900) -> list[str]:
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


class FlightDiscordClient(discord.Client):
    async def on_ready(self) -> None:
        user = self.user
        name = user.name if user else "bot"
        logger.info("Discord bot logged in as %s — ready for !flight / @mentions", name)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        # Without "Message Content Intent" in the Developer Portal, guild message text is empty → bot cannot read !flight.
        if message.guild and not (message.content or "").strip():
            return
        if not _should_respond(message, self):
            return
        text = _strip_query(message.content, message)
        if not text:
            pfx = _command_prefix()
            await message.channel.send(
                f"Ask for flights in natural language, e.g. `Paris to Berlin on 2026-08-12`. "
                f"In servers, start with `{pfx}` or @mention me."
            )
            return

        key = _conversation_key(message)
        prior = [dict(x) for x in _history[key]]

        try:
            graph = get_agent_graph()
        except AgentConfigurationError as e:
            await message.channel.send(f"Agent is not configured: {e}")
            return

        async with message.channel.typing():
            try:
                reply = await run_agent(graph, prior, text)
            except Exception as e:  # noqa: BLE001
                logger.exception("Agent error in Discord")
                await message.channel.send(f"Something went wrong running the agent: {e}")
                return

        _history[key].append({"role": "user", "content": text})
        _history[key].append({"role": "assistant", "content": reply})

        for i, part in enumerate(_chunk_discord(reply)):
            if i > 0:
                await asyncio.sleep(0.3)
            await message.channel.send(part)


def _intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True  # privileged — enable in Developer Portal
    intents.dm_messages = True
    return intents


def _ssl_context_for_aiohttp() -> ssl.SSLContext:
    """
    discord.py → aiohttp → TLS. macOS python.org: truststore alone can still miss roots;
    always load certifi’s Mozilla bundle as well.
    """
    if settings.discord_insecure_ssl:
        logger.warning(
            "DISCORD_INSECURE_SSL enabled: TLS verification is OFF for Discord (local dev only, insecure)"
        )
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    cafile = certifi.where()
    if sys.platform == "darwin":
        try:
            import truststore

            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.load_verify_locations(cafile=cafile)
            return ctx
        except Exception as e:  # noqa: BLE001
            logger.warning("truststore+certifi failed (%s); using certifi-only TLS for Discord", e)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile=cafile)
    return ctx


def create_client() -> FlightDiscordClient:
    connector = aiohttp.TCPConnector(ssl=_ssl_context_for_aiohttp())
    return FlightDiscordClient(intents=_intents(), connector=connector)


async def run_discord_bot(token: str) -> None:
    client = create_client()
    try:
        await client.start(token)
    except asyncio.CancelledError:
        logger.info("Discord bot task cancelled; closing client…")
        await client.close()
        raise
