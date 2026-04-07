"""Heuristics to check that a model reply still reflects tool-sourced flight facts (prices)."""

from __future__ import annotations

import re

# Matches **12.34 GBP** as produced by format_offers
_TOOL_PRICE_PATTERN = re.compile(
    r"\*\*(?P<amt>[\d.]+)\s+(?P<cur>[A-Z]{3})\*\*",
    re.MULTILINE,
)


def extract_tool_price_tags(tool_output: str) -> list[tuple[str, str]]:
    """Return (amount, currency) pairs from formatted offer lines."""
    return [(m.group("amt"), m.group("cur")) for m in _TOOL_PRICE_PATTERN.finditer(tool_output or "")]


def missing_price_mentions(tool_output: str, reply: str) -> list[str]:
    """
    For each price highlighted in the tool output, ensure the reply still mentions
    the same amount and currency (order-insensitive spacing).
    """
    reply_norm = " ".join((reply or "").split())
    missing: list[str] = []
    for amt, cur in extract_tool_price_tags(tool_output):
        label = f"{amt} {cur}"
        if label in reply_norm:
            continue
        if re.search(re.escape(amt) + r"\s+" + re.escape(cur), reply_norm):
            continue
        missing.append(label)
    return missing


def reply_preserves_tool_prices(tool_output: str, reply: str) -> bool:
    return len(missing_price_mentions(tool_output, reply)) == 0
