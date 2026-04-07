from backend.response_quality import (
    extract_tool_price_tags,
    missing_price_mentions,
    reply_preserves_tool_prices,
)


def test_extract_tool_price_tags():
    tool = "1. **10.00 GBP** — route\n2. **20.50 EUR** — other"
    assert extract_tool_price_tags(tool) == [("10.00", "GBP"), ("20.50", "EUR")]


def test_reply_preserves_prices_ok():
    tool = "1. **99.99 USD** — LHR → CDG"
    reply = "Cheapest is **99.99 USD** on the first option."
    assert reply_preserves_tool_prices(tool, reply)


def test_reply_preserves_prices_detects_hallucinated_amount():
    tool = "1. **99.99 USD** — LHR → CDG"
    reply = "Best price is 100.00 USD."
    assert not reply_preserves_tool_prices(tool, reply)
    assert "99.99 USD" in missing_price_mentions(tool, reply)
