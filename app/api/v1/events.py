from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.event import EventResponse, EventDetailResponse
from app.schemas.seat import SeatResponse
from app.services.event_service import EventService

router = APIRouter(prefix="/events", tags=["Events & Seating"])


@router.get("", response_model=List[EventResponse], summary="List and search events")
async def list_events(
    query: Optional[str] = Query(None, description="Search query in title or description"),
    city: Optional[str] = Query(None, description="Filter by venue city"),
    category: Optional[str] = Query(None, description="Filter by event category"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve scheduled events matching optional filters."""
    events = await EventService.list_events(
        db, query=query, city=city, category=category, limit=limit, offset=offset
    )
    return events


@router.get("/{event_id}", response_model=EventDetailResponse, summary="Get event details")
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Fetch event by ID with its tiers and seat maps."""
    event = await EventService.get_event_by_id(db, event_id=event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} not found",
        )
    return event


@router.get("/{event_id}/available-seats", response_model=List[SeatResponse], summary="Get real-time available seats")
async def get_available_seats(
    event_id: int,
    tier_name: Optional[str] = Query(None, description="Filter by seat tier name"),
    db: AsyncSession = Depends(get_db),
):
    """List available seats for an event in real-time."""
    seats = await EventService.get_available_seats(db, event_id=event_id, tier_name=tier_name)
    # Map tier information to response
    response_seats = []
    for s in seats:
        seat_dict = {
            "id": s.id,
            "event_id": s.event_id,
            "tier_id": s.tier_id,
            "seat_number": s.seat_number,
            "row": s.row,
            "status": s.status,
            "tier_name": s.tier.name if s.tier else None,
            "price": s.tier.price if s.tier else None,
            "hold_expires_at": s.hold_expires_at,
        }
        response_seats.append(SeatResponse(**seat_dict))
    return response_seats

