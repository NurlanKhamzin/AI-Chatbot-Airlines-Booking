import json

from backend.booking import parse_passengers_booking_json


def test_parse_passengers_booking_json_ok():
    raw = json.dumps(
        [
            {
                "passenger_id": "pas_x",
                "title": "mrs",
                "given_name": "Ada",
                "family_name": "Lovelace",
                "gender": "f",
                "born_on": "1990-01-15",
                "email": "ada@example.com",
                "phone_number": "+441234567890",
                "passport_number": "AB1234567",
                "passport_expires_on": "2032-12-31",
                "passport_issuing_country": "gb",
            }
        ]
    )
    pax, err = parse_passengers_booking_json(raw)
    assert err is None
    assert pax is not None and len(pax) == 1
    assert pax[0].id == "pas_x"
    assert pax[0].passport_issuing_country == "GB"


def test_parse_passengers_booking_json_invalid():
    pax, err = parse_passengers_booking_json("not json")
    assert pax is None
    assert err is not None
