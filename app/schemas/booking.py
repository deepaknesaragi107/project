from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict
from app.schemas.seat import SeatResponse


class BookingHoldRequest(BaseModel):
    event_id: int
    seat_ids: List[int]
    user_email: EmailStr
    user_name: str
    user_phone: Optional[str] = None


class BookingConfirmRequest(BaseModel):
    booking_reference: str
    payment_reference: Optional[str] = None


class BookingItemResponse(BaseModel):
    seat_id: int
    seat_number: str
    tier_name: str
    price: Decimal


class BookingResponse(BaseModel):
    id: int
    booking_reference: str
    event_id: int
    event_title: str
    status: str
    total_amount: Decimal
    hold_expires_at: Optional[datetime] = None
    created_at: datetime
    items: List[BookingItemResponse] = []

    model_config = ConfigDict(from_attributes=True)

