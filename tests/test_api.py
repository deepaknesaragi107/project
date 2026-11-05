import datetime
from decimal import Decimal
import pytest
from app.models.event import Venue, Event, SeatTier
from app.models.seat import Seat, SeatStatus


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_booking_hold_and_confirm_flow(async_client, db_session):
    # Seed single event
    now = datetime.datetime.now(datetime.timezone.utc)
    venue = Venue(name="Met Stadium", city="Chicago", address="100 Lakefront", capacity=5000)
    db_session.add(venue)
    await db_session.flush()

    event = Event(title="Rock Fest", category="Concert", event_date=now + datetime.timedelta(days=2), venue_id=venue.id)
    db_session.add(event)
    await db_session.flush()

    tier = SeatTier(event_id=event.id, name="GA", price=Decimal("50.00"), total_seats=2)
    db_session.add(tier)
    await db_session.flush()

    s1 = Seat(event_id=event.id, tier_id=tier.id, seat_number="GA-01", status=SeatStatus.AVAILABLE.value)
    s2 = Seat(event_id=event.id, tier_id=tier.id, seat_number="GA-02", status=SeatStatus.AVAILABLE.value)
    db_session.add_all([s1, s2])
    await db_session.commit()

    # 1. Hold seat GA-01
    hold_payload = {
        "event_id": event.id,
        "seat_ids": [s1.id],
        "user_email": "jane@example.com",
        "user_name": "Jane Doe",
    }
    hold_resp = await async_client.post("/api/v1/bookings/hold", json=hold_payload)
    assert hold_resp.status_code == 201
    hold_data = hold_resp.json()
    assert hold_data["status"] == "PENDING_PAYMENT"
    booking_ref = hold_data["booking_reference"]

    # 2. Try to hold same seat GA-01 again -> Should return 409 CONFLICT
    second_hold = await async_client.post("/api/v1/bookings/hold", json=hold_payload)
    assert second_hold.status_code == 409

    # 3. Confirm booking
    confirm_resp = await async_client.post(
        "/api/v1/bookings/confirm",
        json={"booking_reference": booking_ref},
    )
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert confirm_data["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_chat_assistant_endpoint(async_client, db_session):
    response = await async_client.post(
        "/api/v1/chat",
        json={"message": "What concerts are available?", "session_id": "test-session-1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["session_id"] == "test-session-1"

