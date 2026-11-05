import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin


class SeatStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    BOOKED = "BOOKED"


class Seat(Base, TimestampMixin):
    __tablename__ = "seats"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    tier_id: Mapped[int] = mapped_column(ForeignKey("seat_tiers.id", ondelete="CASCADE"), nullable=False, index=True)
    seat_number: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "A-10", "VIP-1"
    row: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # State & concurrency control
    status: Mapped[str] = mapped_column(String(20), default=SeatStatus.AVAILABLE.value, index=True, nullable=False)
    hold_expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    held_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Optimistic concurrency token
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="seats")
    tier: Mapped["SeatTier"] = relationship("SeatTier", back_populates="seats")

    __table_args__ = (
        UniqueConstraint("event_id", "seat_number", name="uq_event_seat_number"),
        Index("idx_event_seat_status", "event_id", "status"),
    )

