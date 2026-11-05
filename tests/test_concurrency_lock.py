import asyncio
import datetime
from decimal import Decimal
import pytest
from app.models.event import Venue, Event, SeatTier
from app.models.seat import Seat, SeatStatus
from app.services.booking_service import BookingService


@pytest.mark.asyncio
async def test_anti_overbooking_concurrent_holds(db_session):
    """
    Test that when 10 concurrent requests attempt to reserve the EXACT SAME seat,
    exactly ONE request succeeds and 9 receive a conflict.
    """
    # 1. Setup Venue, Event, Tier, Seat
    now = datetime.datetime.now(datetime.timezone.utc)
    venue = Venue(name="Test Arena", city="Test City", address="123 Test St", capacity=1000)
    db_session.add(venue)
    await db_session.flush()

    event = Event(
        title="Exclusive Concert",
        category="Concert",
        event_date=now + datetime.timedelta(days=5),
        venue_id=venue.id,
    )
    db_session.add(event)
    await db_session.flush()

    tier = SeatTier(event_id=event.id, name="VIP", price=Decimal("100.00"), total_seats=1)
    db_session.add(tier)
    await db_session.flush()

    target_seat = Seat(
        event_id=event.id,
        tier_id=tier.id,
        seat_number="VIP-ONLY-1",
        status=SeatStatus.AVAILABLE.value,
    )
    db_session.add(target_seat)
    await db_session.commit()

    seat_id = target_seat.id
    event_id = event.id

    async def attempt(idx: int):
        # Create fresh session for each concurrent transaction
        from tests.conftest import TestingSessionLocal
        async with TestingSessionLocal() as session:
            try:
                bkg = await BookingService.hold_seats(
                    db=session,
                    event_id=event_id,
                    seat_ids=[seat_id],
                    user_email=f"tester_{idx}@example.com",
                    user_name=f"Tester {idx}",
                )
                return True
            except Exception:
                return False

    # Fire 10 concurrent requests
    results = await asyncio.gather(*[attempt(i) for i in range(10)])

    # Assert exactly 1 succeeded
    success_count = sum(1 for r in results if r is True)
    failure_count = sum(1 for r in results if r is False)

    assert success_count == 1, f"Expected exactly 1 successful hold, got {success_count}"
    assert failure_count == 9, f"Expected 9 rejections, got {failure_count}"

