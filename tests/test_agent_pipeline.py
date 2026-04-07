import pytest
from langchain_core.messages import AIMessage
from unittest.mock import AsyncMock, MagicMock

from backend.agent import run_agent


@pytest.mark.asyncio
async def test_run_agent_returns_draft_when_no_reasoner(monkeypatch):
    monkeypatch.setattr("backend.agent.build_reasoning_model", lambda: None)
    graph = MagicMock()
    graph.ainvoke = AsyncMock(
        return_value={"messages": [AIMessage(content="Here is **42.00 EUR** for the flight.")]}
    )
    out = await run_agent(graph, [], "Flights please")
    assert "42.00 EUR" in out


@pytest.mark.asyncio
async def test_run_agent_refine_keeps_prices(monkeypatch):
    """When a reasoner exists, final text should still contain tool-sourced prices."""
    from backend.response_quality import reply_preserves_tool_prices

    draft = "Option 1: **100.00 GBP** direct."

    class FakeReasoner:
        async def ainvoke(self, _msgs):
            class R:
                content = "Summary: the fare is **100.00 GBP** (direct)."

            return R()

    monkeypatch.setattr("backend.agent.build_reasoning_model", lambda: FakeReasoner())
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content=draft)]})
    out = await run_agent(graph, [], "Book cheapest")
    assert reply_preserves_tool_prices(draft, out)
