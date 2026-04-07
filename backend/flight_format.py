"""Format Duffel offer-request response for chat display."""

from __future__ import annotations

from typing import Any


def _segment_summary(seg: dict[str, Any]) -> str:
    dep = (seg.get("origin") or {}).get("iata_code", "?")
    arr = (seg.get("destination") or {}).get("iata_code", "?")
    dep_t = (seg.get("departing_at") or "")[:16].replace("T", " ")
    arr_t = (seg.get("arriving_at") or "")[:16].replace("T", " ")
    oc = (seg.get("operating_carrier") or {}).get("iata_code", "?")
    fn = seg.get("operating_carrier_flight_number") or ""
    flight = f"{oc}{fn}" if fn else str(oc)
    return f"{dep} {dep_t} → {arr} {arr_t} ({flight})"


def format_offers(offer_request_response: dict[str, Any], max_lines: int = 8) -> str:
    data = offer_request_response.get("data") or {}
    offers = data.get("offers") or []
    if not offers:
        return "No flight offers returned. Try other dates or airports (Duffel test mode may limit routes)."

    lines: list[str] = []
    for i, offer in enumerate(offers[:max_lines], start=1):
        total = offer.get("total_amount", "?")
        cur = offer.get("total_currency", "")
        parts: list[str] = []
        for sl in offer.get("slices") or []:
            for seg in sl.get("segments") or []:
                parts.append(_segment_summary(seg))
        route = " | ".join(parts) if parts else "(itinerary unavailable)"
        off_id = (offer.get("id") or "").strip()
        pax_ids = [str(p.get("id", "")).strip() for p in (offer.get("passengers") or []) if p.get("id")]
        id_bits: list[str] = []
        if off_id:
            id_bits.append(f"offer `{off_id}`")
        if pax_ids:
            id_bits.append("passengers " + ", ".join(f"`{x}`" for x in pax_ids))
        suffix = f" — {'; '.join(id_bits)}" if id_bits else ""
        lines.append(f"{i}. **{total} {cur}** — {route}{suffix}")

    extra = len(offers) - max_lines
    if extra > 0:
        lines.append(f"\n… and {extra} more offer(s).")
    return "\n".join(lines)
