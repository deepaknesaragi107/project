import datetime
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.locks import multi_resource_lock, DistributedLock, LockAcquisitionError
from app.models.booking import Booking, BookingItem, BookingStatus
from app.models.event import Event
from app.models.seat import Seat, SeatStatus
from app.models.user import User


class BookingService:
    @staticmethod
    def generate_booking_reference() -> str:
        """Generate human-readable unique booking code."""
        random_suffix = uuid.uuid4().hex[:8].upper()
        return f"BKG-{random_suffix}"

    @classmethod
    async def hold_seats(
        cls,
        db: AsyncSession,
        event_id: int,
        seat_ids: List[int],
        user_email: str,
        user_name: str,
        user_phone: Optional[str] = None,
    ) -> Booking:
        """
        Concurrency-safe seat reservation (Hold phase).
        Uses a two-phase anti-overbooking guarantee:
        1. Redis Distributed Lock on seat IDs (prevents cross-process / cross-pod race conditions)
        2. PostgreSQL SELECT ... FOR UPDATE (pessimistic row-level lock within transaction)
        """
        if not seat_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one seat must be selected.",
            )

        # 1. Acquire Distributed Locks for all requested seats in sorted order
        lock_keys = [f"seat:{sid}" for sid in seat_ids]

        try:
            async with multi_resource_lock(
                lock_keys,
                timeout=settings.LOCK_TIMEOUT_SECONDS,
                acquire_timeout=settings.LOCK_ACQUIRE_TIMEOUT_SECONDS,
            ):
                # 2. Database transaction with row-level locking
                # Verify Event exists
                event = await db.get(Event, event_id)
                if not event or event.status != "SCHEDULED":
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Event not found or not open for booking.",
                    )

                # Fetch seats with row lock: SELECT ... FOR UPDATE
                stmt = (
                    select(Seat)
                    .options(selectinload(Seat.tier))
                    .where(and_(Seat.id.in_(seat_ids), Seat.event_id == event_id))
                    .with_for_update()
                )
                result = await db.execute(stmt)
                locked_seats = list(result.scalars().all())

                if len(locked_seats) != len(seat_ids):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="One or more selected seats do not exist for this event.",
                    )

                now = datetime.datetime.now(datetime.timezone.utc)

                # Check availability of each seat
                unavailable_seats = []
                total_amount = Decimal("0.00")

                for seat in locked_seats:
                    is_active_hold = (
                        seat.status == SeatStatus.HELD.value
                        and seat.hold_expires_at is not None
                        and seat.hold_expires_at > now
                    )
                    is_booked = seat.status == SeatStatus.BOOKED.value

                    if is_booked or is_active_hold:
                        unavailable_seats.append(seat.seat_number)
                    else:
                        total_amount += seat.tier.price

                if unavailable_seats:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Seats {', '.join(unavailable_seats)} are currently reserved or booked by someone else.",
                    )

                # Find or create User
                user_stmt = select(User).where(User.email == user_email)
                user_res = await db.execute(user_stmt)
                user = user_res.scalars().first()

                if not user:
                    user = User(email=user_email, full_name=user_name, phone=user_phone)
                    db.add(user)
                    await db.flush()

                # Calculate hold expiration time
                hold_expires_at = now + datetime.timedelta(minutes=settings.BOOKING_HOLD_EXPIRY_MINUTES)

                # Update seats to HELD state
                for seat in locked_seats:
                    seat.status = SeatStatus.HELD.value
                    seat.hold_expires_at = hold_expires_at
                    seat.held_by_user_id = user.id
                    seat.version += 1

                # Create Booking
                booking_ref = cls.generate_booking_reference()
                booking = Booking(
                    booking_reference=booking_ref,
                    user_id=user.id,
                    event_id=event_id,
                    status=BookingStatus.PENDING_PAYMENT.value,
                    total_amount=total_amount,
                    hold_expires_at=hold_expires_at,
                )
                db.add(booking)
                await db.flush()

                # Create Booking Items
                for seat in locked_seats:
                    item = BookingItem(
                        booking_id=booking.id,
                        seat_id=seat.id,
                        price_at_booking=seat.tier.price,
                    )
                    db.add(item)

                await db.commit()

                # Return populated booking
                return await cls.get_booking_by_reference(db, booking_ref)

        except LockAcquisitionError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"High concurrency detected: {str(e)}",
            )

    @classmethod
    async def confirm_booking(
        cls,
        db: AsyncSession,
        booking_reference: str,
        payment_reference: Optional[str] = None,
    ) -> Booking:
        """Confirm a pending held booking after payment is authorized."""
        # Find booking
        stmt = (
            select(Booking)
            .options(
                selectinload(Booking.items).selectinload(BookingItem.seat),
                selectinload(Booking.event),
            )
            .where(Booking.booking_reference == booking_reference)
        )
        res = await db.execute(stmt)
        booking = res.scalars().first()

        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking reference {booking_reference} not found.",
            )

        if booking.status == BookingStatus.CONFIRMED.value:
            return booking

        if booking.status != BookingStatus.PENDING_PAYMENT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm booking with status '{booking.status}'.",
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        if booking.hold_expires_at and booking.hold_expires_at < now:
            # Mark expired
            booking.status = BookingStatus.EXPIRED.value
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Hold period expired for this reservation. Please choose seats again.",
            )

        seat_ids = [item.seat_id for item in booking.items]
        lock_keys = [f"seat:{sid}" for sid in seat_ids]

        async with multi_resource_lock(lock_keys):
            # Finalize booking
            booking.status = BookingStatus.CONFIRMED.value
            booking.hold_expires_at = None

            # Mark seats as BOOKED permanently
            for item in booking.items:
                item.seat.status = SeatStatus.BOOKED.value
                item.seat.hold_expires_at = None
                item.seat.version += 1

            await db.commit()

        return await cls.get_booking_by_reference(db, booking_reference)

    @classmethod
    async def cancel_booking(cls, db: AsyncSession, booking_reference: str) -> Booking:
        """Cancel an existing booking and release seats back to AVAILABLE."""
        stmt = (
            select(Booking)
            .options(selectinload(Booking.items).selectinload(BookingItem.seat))
            .where(Booking.booking_reference == booking_reference)
        )
        res = await db.execute(stmt)
        booking = res.scalars().first()

        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking {booking_reference} not found.",
            )

        if booking.status in (BookingStatus.CANCELLED.value, BookingStatus.EXPIRED.value):
            return booking

        seat_ids = [item.seat_id for item in booking.items]
        lock_keys = [f"seat:{sid}" for sid in seat_ids]

        async with multi_resource_lock(lock_keys):
            booking.status = BookingStatus.CANCELLED.value
            booking.hold_expires_at = None

            for item in booking.items:
                item.seat.status = SeatStatus.AVAILABLE.value
                item.seat.held_by_user_id = None
                item.seat.hold_expires_at = None
                item.seat.version += 1

            await db.commit()

        return await cls.get_booking_by_reference(db, booking_reference)

    @classmethod
    async def get_booking_by_reference(cls, db: AsyncSession, booking_reference: str) -> Optional[Booking]:
        """Fetch booking with items, seat, tier, and event eagerly loaded."""
        stmt = (
            select(Booking)
            .options(
                selectinload(Booking.user),
                selectinload(Booking.event),
                selectinload(Booking.items)
                .selectinload(BookingItem.seat)
                .selectinload(Seat.tier),
            )
            .where(Booking.booking_reference == booking_reference)
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    @classmethod
    async def release_expired_holds(cls, db: AsyncSession) -> int:
        """Background worker method to sweep expired holds and restore seat availability."""
        now = datetime.datetime.now(datetime.timezone.utc)
        stmt = (
            select(Booking)
            .options(selectinload(Booking.items).selectinload(BookingItem.seat))
            .where(
                Booking.status == BookingStatus.PENDING_PAYMENT.value,
                Booking.hold_expires_at < now,
            )
        )
        res = await db.execute(stmt)
        expired_bookings = list(res.scalars().all())

        released_count = 0
        for bkg in expired_bookings:
            bkg.status = BookingStatus.EXPIRED.value
            for item in bkg.items:
                if item.seat.status == SeatStatus.HELD.value:
                    item.seat.status = SeatStatus.AVAILABLE.value
                    item.seat.held_by_user_id = None
                    item.seat.hold_expires_at = None
                    item.seat.version += 1
                    released_count += 1

        if expired_bookings:
            await db.commit()

        return released_count

