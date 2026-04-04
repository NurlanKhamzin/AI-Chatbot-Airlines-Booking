"""Construct LangChain chat models: DeepSeek (ChatDeepSeek) or OpenAI (ChatOpenAI)."""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.config import settings
from backend.llm_config import effective_llm_provider

logger = logging.getLogger(__name__)


def build_chat_model() -> BaseChatModel:
    """
    DeepSeek: uses langchain-deepseek ChatDeepSeek (LangChain integration).
    OpenAI: ChatOpenAI; optional OPENAI_BASE_URL for Azure or other compatible APIs.

    For LangGraph tool calling, use a model that supports tools. DeepSeek's
    ``deepseek-reasoner`` (R1-style) does not support tool calling — use
    ``deepseek-chat`` (default) for this agent.
    """
    provider = effective_llm_provider()
    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        model = (settings.deepseek_model or "deepseek-chat").strip()
        if "reasoner" in model.lower():
            logger.warning(
                "DEEPSEEK_MODEL=%s may not support tool calling; "
                "use deepseek-chat for the flight agent, or expect failures.",
                model,
            )
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
