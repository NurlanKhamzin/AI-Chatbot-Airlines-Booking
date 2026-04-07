"""Human-readable confirmation after a Duffel order is created."""

from __future__ import annotations

from typing import Any


def _segment_line(seg: dict[str, Any]) -> str:
    dep = (seg.get("origin") or {}).get("iata_code", "?")
    arr = (seg.get("destination") or {}).get("iata_code", "?")
    dep_t = (seg.get("departing_at") or "")[:16].replace("T", " ")
    arr_t = (seg.get("arriving_at") or "")[:16].replace("T", " ")
    mc = (seg.get("marketing_carrier") or {}).get("iata_code", "?")
    fn = seg.get("marketing_carrier_flight_number") or ""
    flight = f"{mc}{fn}" if fn else str(mc)
    return f"{dep} {dep_t} → {arr} {arr_t} ({flight})"


def _order_payload(order_api_response: dict[str, Any]) -> dict[str, Any]:
    return order_api_response.get("data") or order_api_response


def format_order_confirmation(order_api_response: dict[str, Any]) -> str:
    """Summarize a successful ``POST /air/orders`` response for the user (markdown)."""
    data = _order_payload(order_api_response)
    lines: list[str] = ["### Booking confirmed"]

    br = data.get("booking_reference")
    if br:
        lines.append(f"- **Booking reference:** {br}")
    oid = data.get("id")
    if oid:
        lines.append(f"- **Order id:** `{oid}`")

    amt, cur = data.get("total_amount"), data.get("total_currency")
    if amt is not None and cur:
        lines.append(f"- **Total paid:** **{amt} {cur}**")

    pax = data.get("passengers") or []
    if pax:
        names = [
            f"{(p.get('given_name') or '').strip()} {(p.get('family_name') or '').strip()}".strip()
            for p in pax
        ]
        names = [n for n in names if n]
        if names:
            lines.append(f"- **Travelers:** {', '.join(names)}")

    route_parts: list[str] = []
    for sl in data.get("slices") or []:
        for seg in sl.get("segments") or []:
            route_parts.append(_segment_line(seg))
    if route_parts:
        lines.append("- **Itinerary:**")
        lines.extend(f"  - {p}" for p in route_parts)

    lines.append("")
    lines.append("Keep your booking reference for check-in and support.")
    return "\n".join(lines)


def format_order_confirmation_plaintext(order_api_response: dict[str, Any]) -> str:
    """Same itinerary summary as plain text for email (no markdown)."""
    data = _order_payload(order_api_response)
    lines: list[str] = ["BOOKING CONFIRMED", ""]

    br = data.get("booking_reference")
    if br:
        lines.append(f"Booking reference: {br}")
    oid = data.get("id")
    if oid:
        lines.append(f"Order id: {oid}")

    amt, cur = data.get("total_amount"), data.get("total_currency")
    if amt is not None and cur:
        lines.append(f"Total paid: {amt} {cur}")

    pax = data.get("passengers") or []
    if pax:
        names = [
            f"{(p.get('given_name') or '').strip()} {(p.get('family_name') or '').strip()}".strip()
            for p in pax
        ]
        names = [n for n in names if n]
        if names:
            lines.append(f"Travelers: {', '.join(names)}")

    route_parts: list[str] = []
    for sl in data.get("slices") or []:
        for seg in sl.get("segments") or []:
            route_parts.append(_segment_line(seg))
    if route_parts:
        lines.append("")
        lines.append("Itinerary:")
        lines.extend(f"  - {p}" for p in route_parts)

    lines.append("")
    lines.append("Keep your booking reference for check-in and support.")
    return "\n".join(lines)
