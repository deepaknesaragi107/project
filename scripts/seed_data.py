import asyncio
import datetime
from decimal import Decimal
from app.core.database import AsyncSessionLocal, init_db
from app.models.event import Venue, Event, SeatTier
from app.models.seat import Seat, SeatStatus
from app.models.user import User


async def seed():
    print("🌱 Initializing Database Schema...")
    await init_db()

    async with AsyncSessionLocal() as session:
        # Check if already seeded
        from sqlalchemy import select
        existing_venues = (await session.execute(select(Venue))).scalars().first()
        if existing_venues:
            print("Database already has data. Skipping seed.")
            return

        print("🚀 Seeding Venues & Events...")

        # 1. Venues
        v1 = Venue(
            name="D.Y. Patil Stadium",
            city="Mumbai",
            address="Sector 7, Nerul, Navi Mumbai, Maharashtra",
            capacity=55000,
        )
        v2 = Venue(
            name="Wembley Stadium",
            city="London",
            address="London HA9 0WS, United Kingdom",
            capacity=90000,
        )
        v3 = Venue(
            name="Madison Square Garden",
            city="New York",
            address="4 Pennsylvania Plaza, New York, NY 10001",
            capacity=20000,
        )
        session.add_all([v1, v2, v3])
        await session.flush()

        # 2. Events
        now = datetime.datetime.now(datetime.timezone.utc)
        e1 = Event(
            title="Coldplay: Music of the Spheres World Tour",
            description="Experience Coldplay live featuring Chris Martin with stadium laser shows and wristbands.",
            category="Concert",
            event_date=now + datetime.timedelta(days=14),
            venue_id=v1.id,
            status="SCHEDULED",
        )
        e2 = Event(
            title="Taylor Swift: The Eras Tour",
            description="Taylor Swift performing a journey through the musical eras of her 18-year career.",
            category="Concert",
            event_date=now + datetime.timedelta(days=21),
            venue_id=v2.id,
            status="SCHEDULED",
        )
        e3 = Event(
            title="NBA Championship Finals - Game 7",
            description="The ultimate basketball showdown for the world championship trophy.",
            category="Sports",
            event_date=now + datetime.timedelta(days=7),
            venue_id=v3.id,
            status="SCHEDULED",
        )
        session.add_all([e1, e2, e3])
        await session.flush()

        # 3. Tiers & Seats for Coldplay (Event 1)
        tier_vip = SeatTier(event_id=e1.id, name="VIP Lounge", price=Decimal("250.00"), total_seats=10)
        tier_prem = SeatTier(event_id=e1.id, name="Premium Stand", price=Decimal("120.00"), total_seats=15)
        tier_ga = SeatTier(event_id=e1.id, name="General Admission", price=Decimal("60.00"), total_seats=20)
        session.add_all([tier_vip, tier_prem, tier_ga])
        await session.flush()

        for i in range(1, 11):
            session.add(Seat(
                event_id=e1.id,
                tier_id=tier_vip.id,
                seat_number=f"VIP-{i:02d}",
                row="VIP",
                status=SeatStatus.AVAILABLE.value,
            ))
        for i in range(1, 16):
            session.add(Seat(
                event_id=e1.id,
                tier_id=tier_prem.id,
                seat_number=f"P-{i:02d}",
                row="P",
                status=SeatStatus.AVAILABLE.value,
            ))
        for i in range(1, 21):
            session.add(Seat(
                event_id=e1.id,
                tier_id=tier_ga.id,
                seat_number=f"GA-{i:02d}",
                row="GA",
                status=SeatStatus.AVAILABLE.value,
            ))

        # 4. Tiers & Seats for Taylor Swift (Event 2)
        tier_t1 = SeatTier(event_id=e2.id, name="Diamond Front Row", price=Decimal("350.00"), total_seats=10)
        tier_t2 = SeatTier(event_id=e2.id, name="Club Level", price=Decimal("150.00"), total_seats=15)
        session.add_all([tier_t1, tier_t2])
        await session.flush()

        for i in range(1, 11):
            session.add(Seat(
                event_id=e2.id,
                tier_id=tier_t1.id,
                seat_number=f"DIA-{i:02d}",
                row="Front",
                status=SeatStatus.AVAILABLE.value,
            ))
        for i in range(1, 16):
            session.add(Seat(
                event_id=e2.id,
                tier_id=tier_t2.id,
                seat_number=f"CLUB-{i:02d}",
                row="Club",
                status=SeatStatus.AVAILABLE.value,
            ))

        # 5. Default User
        test_user = User(
            email="alex@example.com",
            full_name="Alex Mercer",
            phone="+1-555-0199",
        )
        session.add(test_user)

        await session.commit()
        print("✅ Seed completed successfully! Events, venues, seat tiers, and seats are ready.")


if __name__ == "__main__":
    asyncio.run(seed())

