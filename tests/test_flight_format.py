from backend.flight_format import format_offers


def test_format_offers_includes_offer_and_passenger_ids():
    payload = {
        "data": {
            "offers": [
                {
                    "id": "off_abc123",
                    "total_amount": "120.50",
                    "total_currency": "USD",
                    "passengers": [{"id": "pas_p1", "type": "adult"}],
                    "slices": [
                        {
                            "segments": [
                                {
                                    "origin": {"iata_code": "LHR"},
                                    "destination": {"iata_code": "JFK"},
                                    "departing_at": "2026-08-10T10:00:00",
                                    "arriving_at": "2026-08-10T18:00:00",
                                    "operating_carrier": {"iata_code": "ZZ"},
                                    "operating_carrier_flight_number": "1",
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    }
    text = format_offers(payload)
    assert "off_abc123" in text
    assert "pas_p1" in text
    assert "**120.50 USD**" in text
