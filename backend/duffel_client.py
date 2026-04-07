"""Duffel Flights API — offer search + place suggestions (developer-friendly vs restricted Kiwi Tequila)."""

from __future__ import annotations

from typing import Any

import httpx

from backend.config import settings


class DuffelError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class DuffelClient:
    """Bearer token auth; test tokens `duffel_test_*` from https://app.duffel.com/"""

    def __init__(self) -> None:
        self._base = (settings.duffel_api_base or "https://api.duffel.com").rstrip("/")
        self._cards_base = (settings.duffel_cards_base or "https://api.duffel.cards").rstrip("/")
        self._key = (settings.duffel_api_key or "").strip()

    def configured(self) -> bool:
        return bool(self._key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Duffel-Version": "v2",
        }

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured():
            raise DuffelError("Set DUFFEL_API_KEY (test token from Duffel dashboard).")
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(f"{self._base}{path}", params=params or {}, headers=self._headers())
        if r.status_code >= 400:
            raise DuffelError(f"Duffel API error: {r.text}", r.status_code)
        return r.json()

    async def _post(self, path: str, json_body: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured():
            raise DuffelError("Set DUFFEL_API_KEY (test token from Duffel dashboard).")
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(
                f"{self._base}{path}",
                params=params or {},
                json=json_body,
                headers=self._headers(),
            )
        if r.status_code >= 400:
            raise DuffelError(f"Duffel API error: {r.text}", r.status_code)
        return r.json()

    async def _post_cards(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        """POST to api.duffel.cards — never log request bodies (PAN/CVC)."""
        if not self.configured():
            raise DuffelError("Set DUFFEL_API_KEY (test token from Duffel dashboard).")
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(
                f"{self._cards_base}{path}",
                json=json_body,
                headers=self._headers(),
            )
        if r.status_code >= 400:
            raise DuffelError(f"Duffel Cards API error: {r.text}", r.status_code)
        return r.json()

    async def create_payment_card(self, card_data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a single-use card record. ``card_data`` is the inner ``data`` object
        (number, cvc, name, expiry_*, address_*, …) per Duffel docs.
        """
        return await self._post_cards("/payments/cards", {"data": card_data})

    async def create_three_d_secure_session(
        self,
        card_id: str,
        resource_id: str,
        services: list[dict[str, Any]] | None = None,
        exception: str | None = None,
    ) -> dict[str, Any]:
        """POST /payments/three_d_secure_sessions — resource_id is usually the offer id ``off_…``."""
        inner: dict[str, Any] = {
            "card_id": card_id.strip(),
            "resource_id": resource_id.strip(),
        }
        if services:
            inner["services"] = services
        if exception:
            inner["exception"] = exception
        return await self._post("/payments/three_d_secure_sessions", {"data": inner})

    async def create_air_order(
        self,
        *,
        order_type: str = "instant",
        selected_offers: list[str],
        passengers: list[dict[str, Any]],
        payments: list[dict[str, Any]] | None = None,
        services: list[dict[str, Any]] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": order_type,
            "selected_offers": selected_offers,
            "passengers": passengers,
        }
        if payments is not None:
            data["payments"] = payments
        if services:
            data["services"] = services
        if metadata:
            data["metadata"] = metadata
        return await self._post("/air/orders", {"data": data})

    async def place_suggestions(self, query: str) -> list[dict[str, Any]]:
        data = await self._get("/places/suggestions", {"query": query.strip()})
        return data.get("data") or []

    async def resolve_iata(self, place: str) -> str | None:
        """Return a 3-letter IATA city or airport code usable in offer slices."""
        q = place.strip()
        if len(q) == 3 and q.isalpha():
            return q.upper()
        places = await self.place_suggestions(q)
        for p in places:
            code = p.get("iata_code")
            if code:
                return str(code).upper()
        return None

    async def flight_offers_search(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        return_date: str | None = None,
    ) -> dict[str, Any]:
        o = origin.strip().upper()[:3]
        d = destination.strip().upper()[:3]
        passengers = [{"type": "adult"} for _ in range(max(1, min(9, adults)))]
        slices: list[dict[str, str]] = [
            {"origin": o, "destination": d, "departure_date": departure_date.strip()},
        ]
        if return_date and return_date.strip():
            slices.append(
                {
                    "origin": d,
                    "destination": o,
                    "departure_date": return_date.strip(),
                }
            )
        body = {
            "data": {
                "slices": slices,
                "passengers": passengers,
                "cabin_class": "economy",
            }
        }
        return await self._post(
            "/air/offer_requests",
            body,
            params={"return_offers": "true", "supplier_timeout": "45000"},
        )
