from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.event import Event, Venue, SeatTier
from app.models.seat import Seat, SeatStatus


class EventService:
    @staticmethod
    async def list_events(
        db: AsyncSession,
        query: Optional[str] = None,
        city: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Event]:
        """Search and list events with venue eager-loading."""
        stmt = (
            select(Event)
            .join(Venue, Event.venue_id == Venue.id)
            .options(selectinload(Event.venue), selectinload(Event.tiers))
            .where(Event.status == "SCHEDULED")
            .order_by(Event.event_date.asc())
            .limit(limit)
            .offset(offset)
        )

        if query:
            search_filter = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Event.title).like(search_filter),
                    func.lower(Event.description).like(search_filter),
                    func.lower(Venue.name).like(search_filter),
                )
            )

        if city:
            stmt = stmt.where(func.lower(Venue.city) == city.lower())

        if category:
            stmt = stmt.where(func.lower(Event.category) == category.lower())

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_event_by_id(db: AsyncSession, event_id: int) -> Optional[Event]:
        """Get event by ID with venue, tiers, and seat inventory."""
        stmt = (
            select(Event)
            .options(
                selectinload(Event.venue),
                selectinload(Event.tiers),
                selectinload(Event.seats).selectinload(Seat.tier),
            )
            .where(Event.id == event_id)
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_available_seats(
        db: AsyncSession,
        event_id: int,
        tier_name: Optional[str] = None,
    ) -> List[Seat]:
        """Fetch real-time available seats for an event, considering expired holds as available."""
        now = datetime.now()
        stmt = (
            select(Seat)
            .options(selectinload(Seat.tier))
            .where(
                Seat.event_id == event_id,
                or_(
                    Seat.status == SeatStatus.AVAILABLE.value,
                    (Seat.status == SeatStatus.HELD.value) & (Seat.hold_expires_at < now),
                ),
            )
            .order_by(Seat.seat_number.asc())
        )

        if tier_name:
            stmt = stmt.join(SeatTier, Seat.tier_id == SeatTier.id).where(
                func.lower(SeatTier.name) == tier_name.lower()
            )

        result = await db.execute(stmt)
        return list(result.scalars().all())

