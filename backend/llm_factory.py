"""Construct LangChain chat models: DeepSeek (ChatDeepSeek) or OpenAI (ChatOpenAI)."""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.config import settings
from backend.llm_config import effective_llm_provider

logger = logging.getLogger(__name__)


def _deepseek_tool_model_name() -> str:
    """ReAct requires tool-capable model; map reasoner id to deepseek-chat."""
    name = (settings.deepseek_model or "deepseek-chat").strip()
    if "reasoner" in name.lower():
        logger.warning(
            "DEEPSEEK_MODEL=%s cannot run tools; using deepseek-chat for the agent. "
            "Use DEEPSEEK_REASONING_MODEL for R1.",
            name,
        )
        return "deepseek-chat"
    return name


def build_chat_model() -> BaseChatModel:
    """
    DeepSeek: ChatDeepSeek for LangGraph tool calling (deepseek-chat).
    OpenAI: ChatOpenAI; optional OPENAI_BASE_URL for Azure or other compatible APIs.

    R1 / ``deepseek-reasoner`` does not support tool calls — use ``build_reasoning_model()`` for an optional refine pass.
    """
    provider = effective_llm_provider()
    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        model = _deepseek_tool_model_name()
        return ChatDeepSeek(
            model=model,
            api_key=settings.deepseek_api_key,
            temperature=0.1,
        )

    if provider == "openai":
        llm_kwargs: dict = {
            "model": settings.openai_model,
            "temperature": 0.1,
            "api_key": settings.openai_api_key,
        }
        if settings.openai_base_url.strip():
            llm_kwargs["base_url"] = settings.openai_base_url.strip()
        return ChatOpenAI(**llm_kwargs)

    raise RuntimeError(
        "No LLM configured. Set DEEPSEEK_API_KEY and optionally LLM_PROVIDER=deepseek, "
        "or OPENAI_API_KEY (and LLM_PROVIDER=openai)."
    )


def build_reasoning_model() -> BaseChatModel | None:
    """Optional DeepSeek R1 pass to polish the draft reply (no tools). OpenAI: not used."""
    if effective_llm_provider() != "deepseek":
        return None
    rm = (settings.deepseek_reasoning_model or "").strip()
    if not rm:
        return None
    tool_name = _deepseek_tool_model_name()
    if rm.lower() == tool_name.lower():
        return None
    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(
        model=rm,
        api_key=settings.deepseek_api_key,
        temperature=0.1,
    )
