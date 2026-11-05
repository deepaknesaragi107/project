from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.seat import SeatResponse


class VenueBase(BaseModel):
    name: str
    city: str
    address: str
    capacity: int


class VenueResponse(VenueBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SeatTierResponse(BaseModel):
    id: int
    name: str
    price: Decimal
    total_seats: int
    available_seats: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class EventBase(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    event_date: datetime
    status: str = "SCHEDULED"


class EventCreate(EventBase):
    venue_id: int


class EventResponse(EventBase):
    id: int
    venue_id: int
    venue: VenueResponse
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class EventDetailResponse(EventResponse):
    tiers: List[SeatTierResponse] = []
    seats: List[SeatResponse] = []

    model_config = ConfigDict(from_attributes=True)

