"""Which chat model to use: OpenAI or DeepSeek (LangChain)."""

from __future__ import annotations

from backend.config import settings


def effective_llm_provider() -> str:
    """Returns 'deepseek', 'openai', or 'none'."""
    p = (settings.llm_provider or "auto").strip().lower()
    if p in ("auto", "", "none"):
        if settings.deepseek_api_key.strip():
            return "deepseek"
        if settings.openai_api_key.strip():
            return "openai"
        return "none"
    if p == "deepseek":
        return "deepseek" if settings.deepseek_api_key.strip() else "none"
    if p == "openai":
        return "openai" if settings.openai_api_key.strip() else "none"
    return "none"


def llm_configured() -> bool:
    return effective_llm_provider() in ("deepseek", "openai")
