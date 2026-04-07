import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.booking import CardPaymentDetails, BillingAddress, OrderPassenger, create_instant_order
from backend.booking import ThreeDSChallengeError


@pytest.mark.asyncio
async def test_create_instant_order_balance_calls_duffel():
    d = MagicMock()
    d.create_air_order = AsyncMock(
        return_value={"data": {"id": "ord_1", "booking_reference": "BR1"}}
    )
    pax = [
        OrderPassenger(
            id="pas_1",
            given_name="A",
            family_name="B",
            born_on="1991-05-05",
            email="a@b.co",
            phone_number="+15550001",
        )
    ]
    await create_instant_order(
        d,
        offer_id="off_z",
        total_amount="10.00",
        total_currency="GBP",
        passengers=pax,
        payment_mode="balance",
    )
    d.create_air_order.assert_awaited()
    call_kw = d.create_air_order.await_args.kwargs
    assert call_kw["selected_offers"] == ["off_z"]
    assert call_kw["payments"] == [{"type": "balance", "currency": "GBP", "amount": "10.00"}]
    assert call_kw["passengers"][0]["id"] == "pas_1"


@pytest.mark.asyncio
async def test_create_instant_order_includes_passport_on_passenger():
    d = MagicMock()
    d.create_air_order = AsyncMock(return_value={"data": {"id": "ord_1"}})
    pax = [
        OrderPassenger(
            id="pas_1",
            given_name="A",
            family_name="B",
            born_on="1991-05-05",
            email="a@b.co",
            phone_number="+15550001",
            passport_number="AB1234567",
            passport_expires_on="2030-06-01",
            passport_issuing_country="GB",
        )
    ]
    await create_instant_order(
        d,
        offer_id="off_z",
        total_amount="10.00",
        total_currency="GBP",
        passengers=pax,
        payment_mode="balance",
    )
    sent = d.create_air_order.await_args.kwargs["passengers"][0]
    assert "identity_documents" in sent
    assert sent["identity_documents"][0]["unique_identifier"] == "AB1234567"
    assert sent["identity_documents"][0]["type"] == "passport"


@pytest.mark.asyncio
async def test_create_instant_order_card_three_ds_not_ready():
    d = MagicMock()
    d.create_payment_card = AsyncMock(return_value={"data": {"id": "tcd_1"}})
    d.create_three_d_secure_session = AsyncMock(
        return_value={"data": {"id": "3ds_1", "status": "challenge_required", "client_id": "cli"}}
    )
    pax = [
        OrderPassenger(
            id="pas_1",
            given_name="A",
            family_name="B",
            born_on="1991-05-05",
            email="a@b.co",
            phone_number="+15550001",
        )
    ]
    card = CardPaymentDetails(
        number="4111111111111111",
        name="Test User",
        cvc="123",
        expiry_month="12",
        expiry_year="30",
        address=BillingAddress(
            line_1="1 Main",
            city="London",
            region="London",
            postal_code="SW1A1AA",
            country_code="GB",
        ),
    )
    with pytest.raises(ThreeDSChallengeError) as ei:
        await create_instant_order(
            d,
            offer_id="off_z",
            total_amount="10.00",
            total_currency="GBP",
            passengers=pax,
            payment_mode="card",
            card=card,
        )
    assert ei.value.client_id == "cli"
