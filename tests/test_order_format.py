from backend.order_format import format_order_confirmation, format_order_confirmation_plaintext


def test_format_order_confirmation():
    resp = {
        "data": {
            "id": "ord_1",
            "booking_reference": "ABC12",
            "total_amount": "100.00",
            "total_currency": "EUR",
            "passengers": [{"given_name": "Test", "family_name": "User"}],
            "slices": [
                {
                    "segments": [
                        {
                            "origin": {"iata_code": "CDG"},
                            "destination": {"iata_code": "LHR"},
                            "departing_at": "2026-09-01T08:00:00",
                            "arriving_at": "2026-09-01T09:00:00",
                            "marketing_carrier": {"iata_code": "ZZ"},
                            "marketing_carrier_flight_number": "99",
                        }
                    ]
                }
            ],
        }
    }
    text = format_order_confirmation(resp)
    assert "ABC12" in text
    assert "100.00 EUR" in text
    assert "CDG" in text
    assert "Test User" in text


def test_format_order_confirmation_plaintext_no_markdown():
    resp = {
        "data": {
            "booking_reference": "XY99",
            "total_amount": "1.00",
            "total_currency": "GBP",
        }
    }
    plain = format_order_confirmation_plaintext(resp)
    assert "**" not in plain
    assert "XY99" in plain
    assert "1.00 GBP" in plain
