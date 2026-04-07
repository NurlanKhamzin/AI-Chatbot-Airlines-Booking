"""Instant flight orders via Duffel (balance or card + 3DS)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, TypeAdapter, ValidationError

from backend.config import settings
from backend.duffel_client import DuffelClient, DuffelError


class ThreeDSChallengeError(Exception):
    """3DS session requires a browser challenge — use Duffel Components or a frictionless test card."""

    def __init__(self, client_id: str | None, session_id: str | None, message: str):
        super().__init__(message)
        self.client_id = client_id
        self.session_id = session_id


class BillingAddress(BaseModel):
    line_1: str = Field(..., min_length=1, max_length=200)
    line_2: str | None = Field(None, max_length=200)
    city: str = Field(..., min_length=1, max_length=100)
    region: str = Field(..., min_length=1, max_length=100)
    postal_code: str = Field(..., min_length=1, max_length=20)
    country_code: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2")


class CardPaymentDetails(BaseModel):
    """Raw card fields — only for demos; production should use Duffel Components."""

    number: str = Field(..., min_length=12, max_length=19)
    name: str = Field(..., min_length=1, max_length=120)
    cvc: str = Field(..., min_length=3, max_length=4)
    expiry_month: str = Field(..., min_length=2, max_length=2)
    expiry_year: str = Field(..., min_length=2, max_length=2)
    address: BillingAddress


class OrderPassenger(BaseModel):
    id: str = Field(..., description="Duffel passenger id pas_… from the offer")
    given_name: str = Field(..., min_length=1, max_length=100)
    family_name: str = Field(..., min_length=1, max_length=100)
    gender: Literal["m", "f"] = "m"
    born_on: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    email: str = Field(..., min_length=3, max_length=200)
    phone_number: str = Field(..., min_length=5, max_length=40)
    title: str = Field("mr", max_length=20)
    passport_number: str | None = Field(None, max_length=64)
    passport_expires_on: str | None = Field(
        None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Passport expiry YYYY-MM-DD"
    )
    passport_issuing_country: str | None = Field(
        None, min_length=2, max_length=2, description="ISO 3166-1 alpha-2"
    )


class PassengerBookingJSON(BaseModel):
    """One traveler as collected in chat, before mapping to ``OrderPassenger``."""

    model_config = {"str_strip_whitespace": True}

    passenger_id: str = Field(
        ...,
        validation_alias=AliasChoices("passenger_id", "id", "duffel_passenger_id"),
        description="pas_… from the offer line",
    )
    title: str = Field("mr", max_length=20)
    given_name: str = Field(..., min_length=1, max_length=100)
    family_name: str = Field(..., min_length=1, max_length=100)
    gender: Literal["m", "f"] = "m"
    born_on: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    email: str = Field(..., min_length=3, max_length=200)
    phone_number: str = Field(..., validation_alias=AliasChoices("phone_number", "phone"), min_length=5)
    passport_number: str = Field(..., min_length=3, max_length=64)
    passport_expires_on: str = Field(
        ...,
        validation_alias=AliasChoices("passport_expires_on", "passport_expiry"),
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    passport_issuing_country: str = Field(
        ...,
        validation_alias=AliasChoices("passport_issuing_country", "passport_country"),
        min_length=2,
        max_length=2,
    )

    def to_order_passenger(self) -> OrderPassenger:
        return OrderPassenger(
            id=self.passenger_id.strip(),
            title=self.title.strip(),
            given_name=self.given_name.strip(),
            family_name=self.family_name.strip(),
            gender=self.gender,
            born_on=self.born_on,
            email=self.email.strip(),
            phone_number=self.phone_number.strip(),
            passport_number=self.passport_number.strip(),
            passport_expires_on=self.passport_expires_on,
            passport_issuing_country=self.passport_issuing_country.strip().upper(),
        )


def parse_passengers_booking_json(raw: str) -> tuple[list[OrderPassenger] | None, str | None]:
    """
    Parse a JSON array of passenger objects (see ``PassengerBookingJSON``).
    Returns (passengers, None) or (None, error_message).
    """
    text = (raw or "").strip()
    if not text:
        return None, "passengers_json is empty."
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in passengers_json: {e}"
    if not isinstance(data, list) or len(data) == 0:
        return None, "passengers_json must be a non-empty JSON array of passenger objects."
    adapter = TypeAdapter(list[PassengerBookingJSON])
    try:
        parsed = adapter.validate_python(data)
    except ValidationError as e:
        return None, f"Passenger data invalid: {e}"
    return [p.to_order_passenger() for p in parsed], None


def _passengers_for_duffel(passengers: list[OrderPassenger]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in passengers:
        row: dict[str, Any] = {
            "id": p.id.strip(),
            "title": p.title.strip(),
            "given_name": p.given_name.strip(),
            "family_name": p.family_name.strip(),
            "gender": p.gender,
            "born_on": p.born_on,
            "email": p.email.strip(),
            "phone_number": p.phone_number.strip(),
        }
        if (
            p.passport_number
            and p.passport_expires_on
            and p.passport_issuing_country
        ):
            row["identity_documents"] = [
                {
                    "unique_identifier": p.passport_number.strip(),
                    "type": "passport",
                    "issuing_country_code": p.passport_issuing_country.strip().upper(),
                    "expires_on": p.passport_expires_on,
                }
            ]
        out.append(row)
    return out


def _card_data_payload(card: CardPaymentDetails) -> dict[str, Any]:
    a = card.address
    payload: dict[str, Any] = {
        "number": card.number.strip(),
        "name": card.name.strip(),
        "cvc": card.cvc.strip(),
        "expiry_month": card.expiry_month.strip(),
        "expiry_year": card.expiry_year.strip(),
        "multi_use": False,
        "address_line_1": a.line_1.strip(),
        "address_city": a.city.strip(),
        "address_region": a.region.strip(),
        "address_postal_code": a.postal_code.strip(),
        "address_country_code": a.country_code.strip().upper(),
    }
    line2 = (a.line_2 or "").strip()
    if line2:
        payload["address_line_2"] = line2
    return payload


async def create_instant_order(
    duffel: DuffelClient,
    *,
    offer_id: str,
    total_amount: str,
    total_currency: str,
    passengers: list[OrderPassenger],
    payment_mode: Literal["balance", "card"],
    card: CardPaymentDetails | None = None,
) -> dict[str, Any]:
    """
    Create a paid instant order. ``total_amount`` / ``total_currency`` must match the offer
    (same strings Duffel returned on the offer).
    """
    oid = offer_id.strip()
    cur = total_currency.strip().upper()
    amt = total_amount.strip()
    pax = _passengers_for_duffel(passengers)

    if payment_mode == "balance":
        payments = [{"type": "balance", "currency": cur, "amount": amt}]
    else:
        if card is None:
            raise DuffelError("Card payment requires card details.")
        card_resp = await duffel.create_payment_card(_card_data_payload(card))
        card_row = card_resp.get("data") or {}
        card_id = card_row.get("id")
        if not card_id:
            raise DuffelError("Duffel Cards response missing card id.")

        exc = (settings.duffel_three_ds_exception or "").strip() or None
        session_resp = await duffel.create_three_d_secure_session(
            str(card_id),
            oid,
            exception=exc,
        )
        session = session_resp.get("data") or {}
        status = session.get("status")
        session_id = session.get("id")
        if status != "ready_for_payment":
            raise ThreeDSChallengeError(
                session.get("client_id"),
                str(session_id) if session_id else None,
                f"3DS session status is {status!r}; need ready_for_payment (try a frictionless test card or Duffel Components).",
            )
        payments = [
            {
                "type": "card",
                "currency": cur,
                "amount": amt,
                "three_d_secure_session_id": str(session_id),
            }
        ]

    return await duffel.create_air_order(
        order_type="instant",
        selected_offers=[oid],
        passengers=pax,
        payments=payments,
    )
