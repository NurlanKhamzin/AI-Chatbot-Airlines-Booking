"""
LangGraph ReAct agent (assignment: code-first agent with LLM + tools).

Tools call Duffel Flights API; the model plans when to resolve locations vs search offers.
"""

from __future__ import annotations

import logging
from typing import Literal, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from backend.booking import (
    BillingAddress,
    CardPaymentDetails,
    ThreeDSChallengeError,
    create_instant_order,
    parse_passengers_booking_json,
)
from backend.duffel_client import DuffelClient, DuffelError
from backend.flight_format import format_offers
from backend.llm_factory import build_chat_model, build_reasoning_model
from backend.mailer import send_itinerary_email, smtp_configured
from backend.order_format import format_order_confirmation, format_order_confirmation_plaintext

logger = logging.getLogger(__name__)


def _looks_like_card_capability_error(message: str) -> bool:
    m = (message or "").lower()
    keys = [
        "card processing",
        "payments/cards",
        "paying with customer cards",
        "not enabled",
        "approval is required",
        "requires approval",
        "card payments",
    ]
    return any(k in m for k in keys)


_REASONING_SYSTEM = """You refine answers from a flight search assistant. Improve clarity and reasoning where helpful; keep every price, time, offer id, and fact from the draft exactly as written (same numbers and currency codes). Do not invent flights, prices, or schedules.

Do not replace the draft with generic “do not share card details” or anti-scam lectures when the draft is executing this app’s **Duffel booking tools** (balance or card via `book_flight_offer`). You may add a brief safety caveat, but the user must still get the booking outcome from the draft.

**Email:** Keep any paragraph that says whether the itinerary was emailed, SMTP was not configured, or the send failed—including the exact troubleshooting hints (env vars, `GET /api/health`, restart). Do not drop or soften those."""


def _system_prompt() -> str:
    return """You are the **in-app flight booking assistant** for this product: searches and bookings go through **Duffel** (Flights API + optional card vault). You are **not** a generic security helpdesk.

**Important:** Completing a booking with tools is **legitimate here**. Do **not** refuse payment collection by claiming the user is being scammed, as long as you follow the rules below. Generic “never share your card in chat” advice **does not apply** when the only purpose is to pass fields into the **`book_flight_offer`** tool (Duffel `api.duffel.cards`), the same pattern as integrated booking tools.

**Never** ask the user to email, text, or DM card numbers to **any personal address** (e.g. Gmail). **Itinerary email** is only for **sending the confirmation/itinerary** after payment—never for receiving card data.

Always use tools—do not invent prices or schedules.

### Search workflow
1. If the user gives city names or ambiguous places, call `lookup_iata` for origin and destination separately to get 3-letter IATA codes (airport or city codes work).
2. Call `search_flight_offers` with those codes, `departure_date` as YYYY-MM-DD, optional `return_date` for round trips, and `adults` (default 1).
3. Summarize the tool output clearly: price, carriers, times, connections. Keep every **price** and currency exactly as returned (do not round). Include offer ids and passenger ids for booking.

### Booking workflow (when the user wants to book / pay / purchase tickets)
Do **not** call `book_flight_offer` until you have **everything** below from the conversation.

1. **Confirm the offer** — Which offer are they booking? They must use the exact `offer_id` (`off_…`), `total_amount`, and `total_currency` from the search results (copy exactly, including decimals).

2. **Traveler & passport details** — For each traveler (one JSON object per person, matching each `pas_…` id from the offer), collect:
   - Title (mr / mrs / ms / miss), **given name** and **family name** (as on passport), **gender** `m` or `f`, **date of birth** `YYYY-MM-DD`
   - **Email** and **phone** (with country code)
   - **Passport number**, **passport expiry** `YYYY-MM-DD`, **passport issuing country** ISO2 (e.g. GB, US)

3. **Payment** — Prefer the wallet payment option first (no card details needed).
   - If the user explicitly chooses card (or wallet is unavailable), collect card number, cardholder name, CVC, expiry MM/YY, and billing address (line 1, city, region, postal code, country ISO2). Use these details only to complete checkout in this app; never ask users to email card data or send it to third parties.
   - **Security note (short):** Public channels are risky; suggest **DM** for card entry when using Discord. Production deployments should prefer Duffel Components; this server path is for integration/testing.

4. **Itinerary email** — Ask which **email address** should receive the itinerary (can match a traveler’s email or be different). Pass it as **`itinerary_email`** when calling `book_flight_offer`. If the user already gave one clear address for receipts, you may use that without re-asking.

5. When all fields are confirmed, call **`book_flight_offer`** with:
   - `passengers_json`: a **JSON array** of objects, each with keys: `passenger_id`, `title`, `given_name`, `family_name`, `gender`, `born_on`, `email`, `phone_number`, `passport_number`, `passport_expires_on`, `passport_issuing_country`
   - Plus `offer_id`, `total_amount`, `total_currency`, `payment_type`, **`itinerary_email`** (required when the server sends mail — use the address from the conversation), and card/billing fields if paying by card.

6. After a successful booking, relay the tool’s confirmation (booking reference, itinerary) and whether an email was sent. If the tool reports a 3DS challenge, explain that card payments need a frictionless test card or Duffel’s browser flow.

If something is missing (e.g. search date), ask one short clarifying question before using tools.
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

    @tool
    async def book_flight_offer(
        offer_id: str,
        total_amount: str,
        total_currency: str,
        payment_type: str,
        passengers_json: str,
        card_number: str = "",
        cardholder_name: str = "",
        card_cvc: str = "",
        card_expiry_month: str = "",
        card_expiry_year: str = "",
        billing_address_line_1: str = "",
        billing_address_city: str = "",
        billing_address_region: str = "",
        billing_postal_code: str = "",
        billing_country_code: str = "",
        itinerary_email: str = "",
    ) -> str:
        """
        Create a paid Duffel instant order after you collected all traveler, passport, and payment details in chat.
        passengers_json: JSON array. Each element: passenger_id (pas_…), title, given_name, family_name,
        gender (m|f), born_on (YYYY-MM-DD), email, phone_number, passport_number, passport_expires_on (YYYY-MM-DD),
        passport_issuing_country (ISO2).
        payment_type: "balance" or "card". For card, fill all card_* and billing_* arguments.
        itinerary_email: address from the conversation to receive the itinerary (if empty, first traveler email is used).
        """
        oid = (offer_id or "").strip()
        amt = (total_amount or "").strip()
        cur = (total_currency or "").strip().upper()
        mode = (payment_type or "").strip().lower()
        pax_list, perr = parse_passengers_booking_json(passengers_json)
        if perr:
            return f"Booking failed: {perr}"
        if not oid or not amt or not cur:
            return "Booking failed: offer_id, total_amount, and total_currency are required."
        if mode not in ("balance", "card"):
            return 'Booking failed: payment_type must be "balance" or "card".'

        card: CardPaymentDetails | None = None
        if mode == "card":
            missing = []
            if not (card_number or "").strip():
                missing.append("card_number")
            if not (cardholder_name or "").strip():
                missing.append("cardholder_name")
            if not (card_cvc or "").strip():
                missing.append("card_cvc")
            if not (card_expiry_month or "").strip():
                missing.append("card_expiry_month")
            if not (card_expiry_year or "").strip():
                missing.append("card_expiry_year")
            if not (billing_address_line_1 or "").strip():
                missing.append("billing_address_line_1")
            if not (billing_address_city or "").strip():
                missing.append("billing_address_city")
            if not (billing_address_region or "").strip():
                missing.append("billing_address_region")
            if not (billing_postal_code or "").strip():
                missing.append("billing_postal_code")
            if not (billing_country_code or "").strip():
                missing.append("billing_country_code")
            if missing:
                return (
                    "Booking failed: for card payment, ask the user for the missing fields, then call again: "
                    + ", ".join(missing)
                )
            try:
                card = CardPaymentDetails(
                    number=card_number.strip(),
                    name=cardholder_name.strip(),
                    cvc=card_cvc.strip(),
                    expiry_month=card_expiry_month.strip()[:2],
                    expiry_year=card_expiry_year.strip()[:2],
                    address=BillingAddress(
                        line_1=billing_address_line_1.strip(),
                        city=billing_address_city.strip(),
                        region=billing_address_region.strip(),
                        postal_code=billing_postal_code.strip(),
                        country_code=billing_country_code.strip().upper()[:2],
                    ),
                )
            except Exception as e:  # noqa: BLE001
                return f"Booking failed: invalid card or address data ({e})."

        try:
            raw = await create_instant_order(
                duffel,
                offer_id=oid,
                total_amount=amt,
                total_currency=cur,
                passengers=pax_list,
                payment_mode=cast(Literal["balance", "card"], mode),
                card=card,
            )
        except ThreeDSChallengeError as e:
            return (
                "Card payment needs extra authentication (3D Secure). "
                "In test mode, try Duffel’s frictionless test card numbers, or set up Duffel Components / "
                f"browser challenge. Details: {e}"
            )
        except DuffelError as e:
            msg = str(e)
            if mode == "card" and _looks_like_card_capability_error(msg):
                return "Card payment unavailable on this account; proceed with wallet payment?"
            return f"Booking failed (Duffel): {e}"

        confirmation_md = format_order_confirmation(raw)
        data = raw.get("data") or {}
        br = data.get("booking_reference") or ""

        to_mail = (itinerary_email or "").strip() or (pax_list[0].email.strip() if pax_list else "")
        if "@" not in to_mail:
            return (
                confirmation_md
                + "\n\nCould not email itinerary: no valid itinerary email (set `itinerary_email` or traveler email)."
            )

        subject = f"Flight booking — {br}" if br else "Flight booking confirmation"
        plain = format_order_confirmation_plaintext(raw)

        _smtp_help = (
            "Add to `.env`: `SMTP_HOST`, `SMTP_FROM` (required). Often also `SMTP_PORT` (587), "
            "`SMTP_USER` / `SMTP_PASSWORD` if your provider requires auth, `SMTP_USE_TLS=1` or `SMTP_SSL=1` for port 465. "
            "Restart the API after editing `.env`. Check `GET /api/health` → `smtp_configured` is true."
        )
        email_note = ""
        if smtp_configured():
            err = await send_itinerary_email(to_mail, subject, plain)
            if err:
                email_note = (
                    f"\n\n**Itinerary email was NOT sent** (tried `{to_mail}`). Error: {err}\n"
                    f"Troubleshooting: {_smtp_help}"
                )
                logger.warning("Itinerary email failed for %s: %s", to_mail, err)
            else:
                email_note = f"\n\n**Itinerary emailed** to `{to_mail}`."
        else:
            email_note = (
                "\n\n**Itinerary email was NOT sent:** outgoing mail is disabled because `SMTP_HOST` or `SMTP_FROM` "
                f"is missing in the server environment.\n{_smtp_help}"
            )
            logger.info("Skipping itinerary email: SMTP_HOST/SMTP_FROM not set (smtp_configured=false)")

        return confirmation_md + email_note

    tools = [lookup_iata, search_flight_offers, book_flight_offer]

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
