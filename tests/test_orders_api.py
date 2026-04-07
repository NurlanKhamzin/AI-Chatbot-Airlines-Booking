import pytest
from fastapi.testclient import TestClient

from backend import main


@pytest.fixture
def order_client(monkeypatch):
    monkeypatch.setattr(main.duffel, "configured", lambda: True)

    async def fake_create_instant_order(*_args, **_kwargs):
        return {
            "data": {
                "id": "ord_fixture",
                "booking_reference": "FX123",
                "total_amount": "50.00",
                "total_currency": "GBP",
            }
        }

    monkeypatch.setattr(main, "create_instant_order", fake_create_instant_order)
    return TestClient(main.app)


def test_post_order_success(order_client):
    body = {
        "offer_id": "off_test",
        "total_amount": "50.00",
        "total_currency": "GBP",
        "payment_type": "balance",
        "passengers": [
            {
                "id": "pas_x",
                "given_name": "Ada",
                "family_name": "Lovelace",
                "gender": "f",
                "born_on": "1990-01-15",
                "email": "ada@example.com",
                "phone_number": "+441234567890",
            }
        ],
    }
    r = order_client.post("/api/orders", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["order_id"] == "ord_fixture"
    assert data["booking_reference"] == "FX123"


def test_post_order_card_without_details_422(order_client):
    body = {
        "offer_id": "off_test",
        "total_amount": "50.00",
        "total_currency": "GBP",
        "payment_type": "card",
        "passengers": [
            {
                "id": "pas_x",
                "given_name": "Ada",
                "family_name": "Lovelace",
                "gender": "f",
                "born_on": "1990-01-15",
                "email": "ada@example.com",
                "phone_number": "+441234567890",
            }
        ],
    }
    r = order_client.post("/api/orders", json=body)
    assert r.status_code == 422


def test_post_order_duffel_not_configured(monkeypatch):
    monkeypatch.setattr(main.duffel, "configured", lambda: False)
    client = TestClient(main.app)
    body = {
        "offer_id": "off_test",
        "total_amount": "50.00",
        "total_currency": "GBP",
        "payment_type": "balance",
        "passengers": [
            {
                "id": "pas_x",
                "given_name": "Ada",
                "family_name": "Lovelace",
                "gender": "f",
                "born_on": "1990-01-15",
                "email": "ada@example.com",
                "phone_number": "+441234567890",
            }
        ],
    }
    r = client.post("/api/orders", json=body)
    assert r.status_code == 503
