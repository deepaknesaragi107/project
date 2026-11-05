from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict


class SeatBase(BaseModel):
    seat_number: str
    row: Optional[str] = None
    status: str


class SeatResponse(SeatBase):
    id: int
    event_id: int
    tier_id: int
    tier_name: Optional[str] = None
    price: Optional[Decimal] = None
    hold_expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

