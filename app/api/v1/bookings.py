from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.booking import (
    BookingHoldRequest,
    BookingConfirmRequest,
    BookingResponse,
    BookingItemResponse,
)
from app.services.booking_service import BookingService

router = APIRouter(prefix="/bookings", tags=["Bookings & Concurrency Locks"])


def _map_booking_to_response(booking) -> BookingResponse:
    """Helper to convert ORM Booking model to Pydantic BookingResponse."""
    items_response = [
        BookingItemResponse(
            seat_id=item.seat_id,
            seat_number=item.seat.seat_number,
            tier_name=item.seat.tier.name if item.seat and item.seat.tier else "General",
            price=item.price_at_booking,
        )
        for item in booking.items
    ]
    return BookingResponse(
        id=booking.id,
        booking_reference=booking.booking_reference,
        event_id=booking.event_id,
        event_title=booking.event.title if booking.event else "Event",
        status=booking.status,
        total_amount=booking.total_amount,
        hold_expires_at=booking.hold_expires_at,
        created_at=booking.created_at,
        items=items_response,
    )


@router.post(
    "/hold",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Hold seats (Concurrency-safe via Redis Distributed Lock)",
)
async def hold_seats(
    payload: BookingHoldRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Reserve seats temporarily (10-minute hold window).
    Protected against race conditions / double-booking by Redis Distributed Locks
    and PostgreSQL row-level locks.
    """
    booking = await BookingService.hold_seats(
        db=db,
        event_id=payload.event_id,
        seat_ids=payload.seat_ids,
        user_email=payload.user_email,
        user_name=payload.user_name,
        user_phone=payload.user_phone,
    )
    return _map_booking_to_response(booking)


@router.post(
    "/confirm",
    response_model=BookingResponse,
    summary="Confirm held booking after payment",
)
async def confirm_booking(
    payload: BookingConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    """Confirm a pending reservation, converting held seats into booked seats permanently."""
    booking = await BookingService.confirm_booking(
        db=db,
        booking_reference=payload.booking_reference,
        payment_reference=payload.payment_reference,
    )
    return _map_booking_to_response(booking)


@router.post(
    "/{booking_reference}/cancel",
    response_model=BookingResponse,
    summary="Cancel a booking and release seats",
)
async def cancel_booking(
    booking_reference: str,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a booking, immediately releasing its seats back to AVAILABLE."""
    booking = await BookingService.cancel_booking(
        db=db,
        booking_reference=booking_reference,
    )
    return _map_booking_to_response(booking)


@router.get(
    "/{booking_reference}",
    response_model=BookingResponse,
    summary="Get booking details",
)
async def get_booking(
    booking_reference: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full booking information by reference code."""
    booking = await BookingService.get_booking_by_reference(
        db=db,
        booking_reference=booking_reference,
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_reference} not found",
        )
    return _map_booking_to_response(booking)

