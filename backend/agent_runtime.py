"""Shared Duffel client + compiled LangGraph graph for FastAPI and Discord."""

from __future__ import annotations

from backend.agent import build_flight_agent
from backend.duffel_client import DuffelClient
from backend.config import settings
from backend.llm_config import effective_llm_provider, llm_configured

duffel = DuffelClient()
_agent_graph = None


class AgentConfigurationError(RuntimeError):
    """Raised when LLM or flight API credentials are missing."""


def get_agent_graph():
    """Lazy-init compiled LangGraph agent (requires LLM key + Duffel API key for tools)."""
    global _agent_graph
    if _agent_graph is None:
        if not llm_configured():
            raise AgentConfigurationError(
                "Set DEEPSEEK_API_KEY or OPENAI_API_KEY in .env — the agent requires an LLM."
            )
        if not duffel.configured():
            raise AgentConfigurationError(
                "Set DUFFEL_API_KEY in .env (create a test token at https://app.duffel.com/)."
            )
        _agent_graph = build_flight_agent(duffel)
    return _agent_graph


def agent_ready() -> bool:
    return llm_configured() and duffel.configured()


def llm_provider_label() -> str:
    return effective_llm_provider()
