"""
LangGraph ReAct agent (assignment: code-first agent with LLM + tools).

Tools call Duffel Flights API; the model plans when to resolve locations vs search offers.
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from backend.duffel_client import DuffelClient, DuffelError
from backend.flight_format import format_offers
from backend.llm_factory import build_chat_model, build_reasoning_model

logger = logging.getLogger(__name__)

_REASONING_SYSTEM = """You refine answers from a flight search assistant. Improve clarity and reasoning where helpful; keep every price, time, and fact from the draft. Do not invent flights, prices, or schedules."""


def _system_prompt() -> str:
    return """You are a flight search assistant backed by Duffel flight offers (test or live mode per your API key).

Always use tools—do not invent prices or schedules.
Workflow:
1. If the user gives city names or ambiguous places, call `lookup_iata` for origin and destination separately to get 3-letter IATA codes (airport or city codes work).
2. Call `search_flight_offers` with those codes, `departure_date` as YYYY-MM-DD, optional `return_date` for round trips, and `adults` (default 1).
3. Summarize the tool output clearly for the user: price, carriers, times, and connections when shown.

If something is missing (e.g. date), ask one short clarifying question before calling search.
Be concise; use markdown **bold** for prices and key facts when helpful."""


def build_flight_agent(duffel: DuffelClient):
    """Create a compiled LangGraph agent that uses async Duffel tools."""

    @tool
    async def lookup_iata(location: str) -> str:
        """Resolve a city, airport name, or IATA-like string to a 3-letter IATA code. Call for each origin and destination."""
        loc = (location or "").strip()
        if not loc:
            return "Error: empty location."
        try:
            code = await duffel.resolve_iata(loc)
        except DuffelError as e:
            return f"Lookup failed: {e}"
        if not code:
            return f"No IATA code found for “{location}”. Ask the user for a nearby major airport or a 3-letter code."
        return f"IATA code: {code.upper()} (for “{location}”)"

    @tool
    async def search_flight_offers(
        origin_iata: str,
        destination_iata: str,
        departure_date: str,
        return_date: str = "",
        adults: int = 1,
    ) -> str:
        """Search flight offers. origin_iata and destination_iata must be 3-letter IATA codes. departure_date is YYYY-MM-DD. return_date optional for round trip."""
        o = (origin_iata or "").strip().upper()[:3]
        d = (destination_iata or "").strip().upper()[:3]
        dep = (departure_date or "").strip()
        ret = (return_date or "").strip() or None
        if len(o) != 3 or len(d) != 3:
            return "Error: origin and destination must be valid 3-letter IATA codes. Use lookup_iata first."
        try:
            n = max(1, min(9, int(adults)))
        except (TypeError, ValueError):
            n = 1
        try:
            payload = await duffel.flight_offers_search(
                origin=o,
                destination=d,
                departure_date=dep,
                adults=n,
                return_date=ret,
            )
        except DuffelError as e:
            return f"Flight search failed: {e}"
        return format_offers(payload)

    tools = [lookup_iata, search_flight_offers]

    llm = build_chat_model()

    return create_react_agent(llm, tools, prompt=_system_prompt())


def history_to_messages(
    history: list[dict[str, str]], latest_user: str
) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for m in history:
        role, content = m.get("role", ""), m.get("content", "")
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
    out.append(HumanMessage(content=latest_user))
    return out


def _aimessage_to_text(msg: AIMessage) -> str:
    text = msg.content
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts = []
        for block in text:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts) or "(No text response.)"
    return str(text)


async def run_agent(
    graph,
    history: list[dict[str, str]],
    user_message: str,
) -> str:
    messages = history_to_messages(history, user_message)
    result = await graph.ainvoke({"messages": messages})
    final = result["messages"][-1]
    if isinstance(final, AIMessage):
        draft = _aimessage_to_text(final)
    else:
        draft = str(getattr(final, "content", final))

    reasoner = build_reasoning_model()
    if reasoner is None:
        return draft
    try:
        refined = await reasoner.ainvoke(
            [
                SystemMessage(content=_REASONING_SYSTEM),
                HumanMessage(content=draft),
            ]
        )
        content = refined.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            joined = "".join(parts).strip()
            if joined:
                return joined
    except Exception as e:  # noqa: BLE001
        logger.warning("DeepSeek reasoning pass failed, using draft reply: %s", e)
    return draft
